#!/usr/bin/python3

# Munic - simple web-based music server

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import threading
from urllib import parse as urllibparse
import base64
import sys
import os
import unicodedata
import math
import mimetypes
import logging
import pathlib
import re
import random
import subprocess
import time
import weakref
#import code # For code.interact()

# Whether to use HTTPS
USE_HTTPS = False

# Maximum number of simultaneous transcodes to allow (or 0 to not allow transcoding)
MAX_SIMULTANEOUS_TRANSCODES = 1

# Maximum number of completed transcodes to preserve
MAX_COMPLETED_TRANSCODES = 20

# The directories in which to look for media
media_dirs = []

# Data structure containing the media library 
library = None

# Location of this sript
script_path = None

# Ongoing media GETs - for debug
media_gets = {}

# The cache of transcoders: a dictionary of requestedFilepath:transcoderObject, using weak references
transcoders_cache = weakref.WeakValueDictionary()

# The running transcoders we want to keep alive (MAX_SIMULTANEOUS_TRANSCODES)
running_transcoders_to_keep = []

# The completed transcode jobs we want to keep (MAX_COMPLETED_TRANSCODES)
completed_transcoders_to_keep = []

class Transcoder:
    # Index for the next transcode temp file
    nextIndex = 0

    # TODO use a proper temp directory
    TRANSCODE_DIR = os.path.dirname(os.path.realpath(__file__))

    """ Clean up leftover transcodes """
    def CleanUp():
        logging.info("Cleaning up old transcoded files")
        for old_transcode in pathlib.Path(Transcoder.TRANSCODE_DIR).glob("TRANSCODE_*.*"):
            logging.debug("Removing old transcode output {}".format(old_transcode))
            os.remove(os.path.join(Transcoder.TRANSCODE_DIR, str(old_transcode)))

    """ Constructor """
    def __init__(self, requested_filepath, source_filepath, target_extension):
        self.finished = False
        self.requested_filepath = requested_filepath

        out_file = "TRANSCODE_{}{}".format(Transcoder.nextIndex, target_extension)
        Transcoder.nextIndex += 1

        logging.info("Creating transcode session for {} -> {} (Temp file: {})".format(source_filepath, target_extension, out_file))

        self.out_file = os.path.join(Transcoder.TRANSCODE_DIR, out_file)

        # Delete the file if it exists (probably left over from a previous session)
        if os.path.exists(self.out_file):
            os.remove(self.out_file)

        # Start the transcode
        # The "-flush_packets 1" argument causes the output to be written to the file more quickly, rather than being buffered.
        # This helps speed up and avoid glitches at the start of playback if running on slow hardware (e.g. raspberry pi zero).
        # The "-vn" argument ensures we do not put video in the output, which can mean the entire file must be transcoded
        # before anything is written to disk.
        # The "-v quiet" supresses output -- nobody will read it anyway, and it can leave the console in a bad state if cancelled.
        self.transcode_process = subprocess.Popen(["ffmpeg", "-v", "quiet", "-i", source_filepath, "-vn", "-flush_packets", "1", self.out_file],
                                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    """ Destructor """
    def __del__(self):
        logging.info("Destructing transcode job for {} -> {}".format(self.requested_filepath, self.out_file))

        # Stop the active transcode
        if not self.transcode_finished():
            self.transcode_process.terminate()

        # Remove the output file from disk
        if os.path.exists(self.out_file):
            os.remove(self.out_file)

    """ Has the transcoding completed? """
    def transcode_finished(self):
        if self.finished:
            return True
        if self.transcode_process.poll() is not None:
            self.finished = True
            self.transcode_process = None

        return self.finished

    """ Returns the name of the transcoded file.  Waits for it to be created if it does not already exist. """
    def get_transcoded_filepath(self):
        # If we have finished transcoding, the file should have been created already 
        if self.transcode_finished():
            if os.path.exists(self.out_file):
                return self.out_file
            else:
                logging.warning("Transcode finished but destination file not created")
                return None

        # If we are still transcoding, wait up to 10s for the file to appear
        for i in range(0,100):
            if os.path.exists(self.out_file):
                return self.out_file
            time.sleep(0.1)

        return None

class Handler(BaseHTTPRequestHandler):

    """ Constructor """
    def __init__(self, request, client_address, server):
        # Override the default protocol (HTTP/1.0).
        # Note that this means we MUST provide an accurate Content-Length header!
        self.protocol_version = "HTTP/1.1"

        # Call the BaseHTTPRequestHandler constructor
        super(Handler, self).__init__(request, client_address, server)

    def do_GET(self):
        logging.info("GET path: {} on thread {}".format(self.path, threading.get_ident()))

        name = urllibparse.unquote(self.path)

        # Front page
        if name == "":
            # TODO special case for front page
            self.send_response(200)
            self.end_headers()
            self.wfile.write("Coming soon".encode("utf-8"))
        # If requesting a static file...
        elif name == "/audioPlayer.js":
            self.send_file(os.path.join(script_path, "audioPlayer.js"))
        elif name == "/favicon.png":
            self.send_file(os.path.join(script_path, "favicon.png"))
        elif name == "/munic.png":
            self.send_file(os.path.join(script_path, "munic.png"))
        elif name == "/munic.css":
            self.send_file(os.path.join(script_path, "munic.css"))
        # If the url ends with a "/" or "/*", treat it as a menu/playlist request for that location 
        elif name.endswith("/") or name.endswith("/*"):
            self.send_menu(name)
        # If the url ends with the special case "/_" or "/*_", reload the library
        elif name.endswith("/_") or name.endswith("/*_"):
            self.refresh_library(name)
        # Otherwise, assume the request is for a media file 
        else:
            self.send_media(name)

        logging.info("GET completed: {} on thread {}".format(self.path, threading.get_ident()))

    def refresh_library(self, name):
        logging.info("Refreshing media library")

        # Perform the refresh
        global library
        library = load_library(media_dirs)

        # Redirect the browser to the same location, without the trailing _
        redirect = name[:-1]
        logging.info("Redirecting to " + redirect)
        self.send_response(301)
        self.send_header('Location', redirect)
        self.end_headers()

    def send_menu(self, name):
        # If the request is for a directory, we treat it as requesting a list of subdirs (artists, albums etc.) in that location.
        #   Queen/ --> gives a list of all Queen albums
        # If the request is for the file "*", we treat it as a request for everything (all files and subdirs) in that location.
        #   Queen/* --> gives a list of all Queen albums AND a playlist of all Queen songs.

        include_songs = False
        if name.endswith("/*"):
            include_songs = True

        # The root location, relative to the requested location
        root = ""

        # Get the requested path and navigate to it.
        # As we go, build up "display_name" with the properly-formatted names of the directories.
        # Also keep track of the most specific part of the name, for the title.
        title = "Munic"
        requested_path = name.rstrip("/")
        logging.debug("Requested path: {}".format(requested_path))
        parts = requested_path.split("/")
        base_dict = library
        display_names = []
        dirs = base_dict["dirs"]
        # Remove empty parts which result from splitting empty strings etc.
        parts = [ part for part in parts if part and part != "*"]
        for part in parts:
            # If that directory does not exist
            if part not in dirs.keys():
                logging.warning("Failed to find {} - failed at {}".format(requested_path, part))
                self.send_response(404)
                self.end_headers
                return
            base_dict = dirs[part]
            root += "../"
            display_names.append(base_dict["display_name"])
            title = base_dict["display_name"]
            dirs = base_dict["dirs"]

        # Read the playlist page template html from file
        with open(os.path.join(script_path, "playlist.html")) as html_file:
            html = html_file.read()

        # Construct the page. This will be all the directories directly under this one, as links,
        # and all the files from this directory onwards, as a playlist.

        # Drop in the page title
        html = html.replace("__TITLE__", title)

        # Drop in the audioplayer javascript file
        html = html.replace("__AUDIOPLAY_JS__", root + "audioPlayer.js") 

        # Get the headings: the display names of the path, or "Munic" if none.
        if not display_names:
            display_names.append("Munic")

        # Lazy way to ensure there are enough items in the list to replace the headings
        display_names.append("")
        display_names.append("")

        # Drop in the headings
        for h in range(0,3):
            html = html.replace("__HEADING{}__".format(h), display_names[h])

        # Generate some colours and drop them in
        # TODO Get these from the selected image
        r = [ random.randint(1,3) for a in range (0,9) ]
        colours = [ "#{}{}{}".format(r.pop(), r.pop(), r.pop()) for a in range(0,3) ]
        for c in range(0,3):
            html = html.replace("__BG_COL{}__".format(c), colours[c])

        # Build the playlist (subdir) links section
        playlist_links = ""
        # If we are not showing the songs in the folder, the first link is always "All songs"
        if not include_songs:
            playlist_links = """<div id="speciallink"><p><a href="*">All Songs</a></p></div>"""

        if dirs:
            # Sort the keys (dir names) alphabetically
            # Note that we are sorting by "simplified name", so "The Beatles" is in with the Bs, not the Ts.
            dir_names = [ dir_name for dir_name in dirs.keys() ]
            dir_names.sort()
            for dir_name in dir_names:
                display_name = dirs[dir_name]["display_name"]
                link = dir_name + "/*"  # Include '*' to take us to the playlist
                playlist_link = """<a href="__LINK__"><div><p>__NAME__</p></div></a>""".replace("__LINK__", link).replace("__NAME__", display_name)
                playlist_links = playlist_links + playlist_link

        # Drop the links into the html document
        html = html.replace("__PLAYLIST_LINKS__", playlist_links)

        # Build the playlist contents.  
        playlist_items = ""

        # The path to request to refresh the library
        refresh_path = "_"

        if include_songs:
            # Get all media files at or below this location
            media_items = get_all_songs(base_dict)

            # Construct the list items
            for (song_display_name, song_display_album, song_constructed_filepath, art_constructed_filepath) in media_items:
                playlist_item = """<li><img src="__ALBUMART__"><a href="__SONG_FILENAME__"><p>__SONG_NAME__</p><p>__ALBUM_NAME__</p></a></li>\n""" \
                    .replace("__ALBUMART__", art_constructed_filepath) \
                    .replace("__SONG_FILENAME__", song_constructed_filepath) \
                    .replace("__SONG_NAME__", song_display_name) \
                    .replace("__ALBUM_NAME__", song_display_album)
                playlist_items = playlist_items + playlist_item

            refresh_path = "*_"

        # Drop the playlist content into the html template
        html = html.replace("__PLAYLIST_ITEMS__", playlist_items)

        # Drop in the album art
        art_filepath = get_art_filepath(base_dict)
        if not art_filepath:
            art_filepath = "__ROOT__munic.png"

        html = html.replace("__ALBUMART__", art_filepath);

        # Drop in the redirect path, which is either "_" if we are not showing songs, or "*_" if we are
        html = html.replace("__REFRESH__", refresh_path)

        # Drop in the root location (last, in case it is used in any substituted values)
        html = html.replace("__ROOT__", root)

        self.send_html(html)

    def send_media(self, name):
        logging.debug("Attempting to get file {}".format(name))

        # Get the file range, if specified by the requester
        range_header = self.headers.get("Range")
        range_start = None
        range_end = None
        if range_header:
            logging.debug("Range header: {}".format(range_header))
            match = re.match("bytes[= :](\\d+|)\\-(\\d+|)$", range_header, re.IGNORECASE)
            if match and match.lastindex == 2:
                groups = match.groups()
                range_start = int(groups[0]) if groups[0].isnumeric() else None
                range_end = int(groups[1]) if groups[1].isnumeric() else None 
                logging.debug("Requested range {}-{}".format(range_start, range_end))

        # Get the dict representing the path of the requested file by walking down the structure to the right directory
        parts = name.lstrip("/").split("/")
        base_dict = library
        for dir_part in parts[:-1]:
            dirs = base_dict["dirs"]
            if dir_part not in dirs.keys():
                logging.warning("Requested unknown file: {} - failed at {}".format(name, dir_part))
                self.send_response(404)
                self.end_headers()
                return
            base_dict = dirs[dir_part]

        # Remove the extension from the constructed filename to give the display name
        constructed_filename = parts[-1]
        basename, requested_extension = os.path.splitext(constructed_filename)

        found = False

        # If the requested file is the graphic in this directory
        if constructed_filename == base_dict["graphic_name"]:
            filepath = base_dict["graphic_filepath"]
            self.send_file(filepath, range_start, range_end)
            found = True
        else:
            # Find the song in the dictionary (display name is key) and get its real filepath (the value)
            media = base_dict["media"]
            if basename in media.keys():
                filepath = media[basename][1]

                # If the file is already in the requested format, just send it
                actual_extension = os.path.splitext(filepath)[1]
                if (actual_extension == requested_extension):
                    self.send_file(filepath, range_start, range_end)
                    found = True
                # Otherwise if the requested format is a supported type, transcode and send 
                elif MAX_SIMULTANEOUS_TRANSCODES and requested_extension in (".ogg", ".mp3"):
                    self.send_transcoded_file(name, filepath, requested_extension, range_start, range_end)
                    self.housekeep_transcoders()
                    found = True

        if not found:
            logging.warning("File {}{} not found in library".format(basename, requested_extension))
            self.send_response(404)
            self.end_headers()
            return

    def send_html(self, htmlstr):
        "Simply sends htmlstr with status 200 and the correct content-type and content-length."

        # Encode the HTML
        encoded = htmlstr.encode("utf-8")
        logging.info("Sending HTML ({} bytes)".format(len(encoded)))

        self.send_response(200)
        self.send_header("Content-Length", len(encoded))
        self.send_header("Content-Type", 'text/html; charset=utf-8')
        self.end_headers()

        self.wfile.write(encoded)

    """Send the specified file with status 200. and correct content-type and content-length."""
    def send_file(self, filepath, range_start:int = None, range_end:int = None):
        logging.info("Sending file {}".format(filepath))
        media_gets[threading.get_ident()] = filepath

        # Was a range requested?
        range_requested = True if range_start is not None or range_end is not None else False

        # Get the mime type of the file
        mime_type, encoding = mimetypes.guess_type(filepath)

        with open(filepath, 'rb') as f:
            # If the file is not seekable, send the whole thing.
            # (We could read and discard if this is a problem, but it is not expected to happen.)
            if range_requested and not f.seekable():
                logging.warning("File not seekable: not sending range")
                range_requested = False
                range_start = None
                range_end = None

            # Find the length of the file
            file_length = os.fstat(f.fileno()).st_size
            logging.debug("File length: {}".format(file_length))

            # Populate ranges if not already done
            if range_start is None:
                range_start = 0
            if range_end is None:
                range_end = file_length - 1
            # Sanity check them
            if range_start>range_end or range_start<0 or range_end>=file_length:
                self.send_response(416)
                self.end_headers()
                return

            if range_requested:
                content_length = 1 + range_end - range_start
                logging.info("Sending range {}-{} ({} bytes) out of {}".format(range_start, range_end, content_length, file_length))
                self.send_response(206) # Partial content
                self.send_header("Content-Range", "bytes {}-{}/{}".format(range_start, range_end, file_length))
            else:
                logging.info("Sending entire file")
                content_length = file_length
                self.send_response(200)

            self.send_header("Accept-Ranges", 'bytes')
            self.send_header("Content-Length", content_length)
            self.send_header("Cache-Control", "max-age=1000")
            if mime_type:
                self.send_header("Content-Type", mime_type)
            self.end_headers()

            try:
                # Seek to the desired start (lazily just asusming it worked)
                f.seek(range_start)

                # Read and send 16kB at a time
                total_sent = 0
                while content_length > 0:
                    length_to_read = min(16384, content_length)
                    data = f.read(length_to_read)
                    length_read = len(data)
                    self.wfile.write(data)
                    content_length -= length_read
                    total_sent += length_read

                logging.info("Successfully sent file {}".format(filepath))
            except BrokenPipeError:
                logging.warning("Broken pipe error sending {} after {} bytes".format(filepath, total_sent))
            except ConnectionResetError:
                logging.warning("Connetion reset by peer sending {} after {} bytes".format(filepath, total_sent))
        logging.info("File send finished on thread {}".format(threading.get_ident()))
        media_gets.pop(threading.get_ident())
        logging.debug("Ongoing transfers: " + str(media_gets))

    """ Send the given file, transcoded to the specified format"""
    def send_transcoded_file(self, requested_filepath, source_filepath, requested_extension, range_start:int = None, range_end:int = None):
        logging.info("Sending transcoded file {} -> {}".format(source_filepath, requested_filepath))

        # Get the existing transcoder if it exists
        try:
            transcoder = transcoders_cache[requested_filepath]
        except KeyError:
            # Else create a new one and store it
            transcoder = Transcoder(requested_filepath, source_filepath, requested_extension)
            transcoders_cache[requested_filepath] = transcoder

        # Put the transcoder at the end of the appropriate "to keep" list
        self.refresh_transcoder(transcoder)

        # Housekeep existing transcoders after (possibly) adding one
        self.housekeep_transcoders()

        # Get the name of the transcoded file (also waits for it to be created)
        transcoded_filepath = transcoder.get_transcoded_filepath()

        # If the file was not created, send a 404.  Note that it could just be very slow.
        if not transcoded_filepath:
            logging.warning("Transcoded file not found")
            self.send_response(404)
            self.end_headers
            return

        # If the transcode has already finished, send it as a regular file -- offering ranges
        if transcoder.transcode_finished():
            self.send_file(transcoded_filepath, range_start, range_end)
            return

        # Get the mime type of the transcoded file
        mime_type, encoding = mimetypes.guess_type(requested_filepath)

        with open(transcoded_filepath, 'rb') as f:
            self.send_response(200)
            self.send_header("Cache-Control", "max-age=1000")
            if mime_type:
                self.send_header("Content-Type", mime_type)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            total_sent = 0
            FIRST_CHUNK_SIZE = 131072 # 128kB in first chunk 
            TRANSCODING_CHUNK_SIZE = 65536  # 64kB at a time while transcoding
            TRANSCOMPLETE_CHUNK_SIZE = 131072  # 128kB chunks once transcode has finished
            time.sleep(1)
            try:
                # While we are still transcoding, send a chunk at a time
                chunk_size = FIRST_CHUNK_SIZE
                while not transcoder.transcode_finished():
                    file_length_remaining = os.fstat(f.fileno()).st_size - f.tell()
                    if file_length_remaining >= chunk_size:
                        data = f.read(chunk_size)
                        length_read = len(data)
                        chunk_size_string = "%x\r\n" % length_read
                        self.wfile.write(chunk_size_string.encode("utf-8"))
                        self.wfile.write(data)
                        self.wfile.write("\r\n".encode("utf-8"))
                        self.wfile.flush()
                        total_sent += length_read
                        chunk_size = TRANSCODING_CHUNK_SIZE
                    else:
                        time.sleep(0.5)

                # In case this transcode was not one of the "to keep" ones (becuase there were more than
                # MAX_SIMULTANEOUS_TRANSCODES connections), add it to the completed "to keep" list
                self.refresh_transcoder(transcoder)

                # Send the rest
                chunk_size = TRANSCOMPLETE_CHUNK_SIZE
                # While there is file remaining
                file_remaining = os.fstat(f.fileno()).st_size - f.tell()
                while file_remaining > 0:
                    length_to_read = min(chunk_size, file_remaining)
                    data = f.read(length_to_read)
                    length_read = len(data)
                    chunk_size_string = "%x\r\n" % length_read
                    self.wfile.write(chunk_size_string.encode("utf-8"))
                    self.wfile.write(data)
                    self.wfile.write("\r\n".encode("utf-8"))
                    total_sent += length_read
                    file_remaining = os.fstat(f.fileno()).st_size - f.tell()

                # Send an empty chunk to indicate the end of file
                self.wfile.write("0\r\n\r\n".encode("utf-8"))

                logging.info("Successfully sent transcoded file ({} bytes)".format(total_sent))
            except BrokenPipeError:
                logging.warning("Broken pipe error sending {} after {} bytes".format(requested_filepath, total_sent))
            except ConnectionResetError:
                logging.warning("Connetion reset by peer sending {} after {} bytes".format(requested_filepath, total_sent))

    """ Put the given transcoder at the end of the appropriate to-keep list"""
    def refresh_transcoder(self, transcoder):
        # Remove the transcoder from any of the "to keep" lists it is in.
        # (We will add it at the end below.)
        try:
            running_transcoders_to_keep.remove(transcoder)
        except ValueError:
            pass

        try:
            completed_transcoders_to_keep.remove(transcoder)
        except ValueError:
            pass

        if transcoder.transcode_finished():
            completed_transcoders_to_keep.append(transcoder)
        else:
            running_transcoders_to_keep.append(transcoder)

    """ Housekeep the list of transcoders:
        - Move completed ones to the completed "to keep" list.
        - Remove the oldest in each "to keep" list if we have too many. """
    def housekeep_transcoders(self):
        global running_transcoders_to_keep, completed_transcoders_to_keep
        # Move any completed transcodes from the running to the completed "to keep" list
        for t in running_transcoders_to_keep:
            if t.transcode_finished():
                logging.debug("Moving transcode {} from running list to completed".format(t.requested_filepath))
                running_transcoders_to_keep.remove(t)
                completed_transcoders_to_keep.append(t)

        # Prune the lists of transoders
        running_transcoders_to_keep = running_transcoders_to_keep[-MAX_SIMULTANEOUS_TRANSCODES:]
        completed_transcoders_to_keep = completed_transcoders_to_keep[-MAX_COMPLETED_TRANSCODES:]

        # Items with no remaining references will magically disappear from the transcoders_cache

        logging.debug("Running transcoders to keep: {}, completed: {}, cache: {}"
            .format(len(running_transcoders_to_keep), len(completed_transcoders_to_keep), len(transcoders_cache)))

class ThreadingSimpleServer(ThreadingMixIn, HTTPServer):
    pass

"""Return a simplified (searchable) version of the string, with all accents replaced with un-accented charaters,
all spaces and punctuation removed, leading 'the' removed, and lower-case"""
def simplify(string):
    string = ''.join(c for c in unicodedata.normalize('NFD', string) if unicodedata.category(c) != 'Mn')
    string = string.lower()
    string = re.sub(r"^the\b", "", string, 1)               # Remove leading 'the' (whole word only)
    string = ''.join([c for c in string if c.isalnum()])    # Remove anything non-alpha-numeric
    return string

""" Get a complete, flat list of all songs in the library.
Returns an alphabetical list of tuples of (song display name, album display name, constructed filepath, art constructed filepath).
"Constructed filepath" is the apparent filepath relative to the given dir-dict, e.g. "queen/adayattheraces/drowse.mp3".
"Art constructed filepath" is the path to request for the album art.
(This includes the extension (e.g. .mp3) in case the browser requires it to play the file.)"""
def get_all_songs(dir_dict, constructed_path: str = "", display_path: str = ""):
    media = dir_dict["media"]
    dirs = dir_dict["dirs"]
    art_filepath = get_art_filepath(dir_dict)
    if art_filepath:
        art_filepath = constructed_path + art_filepath
    else:
        # If no graphic found, use the default logo
        art_filepath = "__ROOT__munic.png"

    results = []
    # Get all media files in this directory, sorted alphabetically
    for media_simplified_name in media.keys():
        media_filepath = media[media_simplified_name][1]
        extension = os.path.splitext(media_filepath)[1]
        constructed_filepath = constructed_path + media_simplified_name + extension
        media_display_name = media[media_simplified_name][0]

        # If there is a path, add it on the end (suitably formatted)
        formatted_display_path = display_path.rstrip("/").replace("/", ": ")
        # if formatted_display_path:
        #     media_display_name += " ({})".format(formatted_display_path)
        results.append( (media_display_name, formatted_display_path, constructed_filepath, art_filepath) )
        results.sort(key=lambda tup: tup[0].casefold())

    # Recurse into all sub-dirs (in alphabetical order), appending the directory name to the path
    sub_dirs = [sd for sd in dirs.keys()]
    sub_dirs.sort()
    for sub_dir in sub_dirs:
        sub_dir_dict = dirs[sub_dir]
        sub_dir_display_path = sub_dir_dict["display_name"]
        results = results + get_all_songs(sub_dir_dict, constructed_path + sub_dir + "/", display_path + sub_dir_display_path + "/")

    return results

""" Get album art for a given dictionary.
If there is one at the base level, returns it.
If there is not one at that level, but there is one or more beneath, return one at random.
If there is none, return None """
def get_art_filepath(base_dict):
    # If there is a graphic at this level, use it
    album_art = None
    if base_dict["graphic_name"]:
        album_art = base_dict["graphic_name"]
    # Otherwise get a random image from anywhere below this
    else:
        album_arts = get_all_graphics(base_dict)
        if album_arts:
            album_art = random.choice(album_arts)

    return album_art

""" Get a complete, flat list of all graphics in the library.
Returns a list of constructed filepaths.
"Constructed filepath" is the apparent filepath relative to the given dir-dict, e.g. "Queen/A Day At The Races/folder.jpg".
(This includes the extension (e.g. .jpg).)"""
def get_all_graphics(dir_dict, constructed_path: str = "", display_path: str = ""):
    dirs = dir_dict["dirs"]

    result = []

    # Get graphic file in this directory, if it exists
    if dir_dict["graphic_name"]:
        result.append(constructed_path + dir_dict["graphic_name"])

    # Recurse into all sub-dirs, appending the directory name to the path
    for sub_dir in dirs.keys():
        sub_dir_dict = dirs[sub_dir]
        sub_dir_display_path = sub_dir_dict["display_name"]
        result = result + get_all_graphics(sub_dir_dict, constructed_path + sub_dir + "/", display_path + sub_dir_display_path + "/")

    # Sort alphabetially
    result.sort(key=lambda tup: tup[0].casefold())

    return result


# TODO Remove empty directories (may need to repeat until none are found as diretory may become empty if we remove its only subdir)
def load_library(media_dirs):
    # Walk the given path, creating a data structure as follows:
    # A recursive structure of a dict representing the top level, containing:
    #  - "display_name" (properly-formatted name, for display)
    #  - "media" (dict of simplified-songname:tuple of (songname:filepath) )
    #  - "dirs" (dict of simplified-dirname:directory-dict like the top level)
    #  - "graphic_name" (graphic name, for the HTML/request, if present)
    #  - "graphic_filepath" (graphic local filepath, if present)
    # The filenames will be the full filepath of the file.
    # Directories will be indexed by "simplfied" name: a lower-case, alpha-numeric version of the real name, with the first "the" removed.
    # Because we want to be able to overlay multiple directories, we cannot simply walk and create the structure as we find it.
    # Instead we check whether each directory exists and add it if not.
    # This has the desirable side-effects of merging directories with effectively the same name, and de-duplicating any songs
    # with identical artist/album/name.
    # The location of the bottom level will be that of the script, so that the default graphic can be found.

    known_music_formats = (".mp3", ".mp4", ".m4a", ".ogg", ".wav", ".flac", ".wma")
    known_grapic_formats = (".jpg", ".jpeg", ".gif", ".bmp", ".png")

    graphic_filepath = os.path.join(script_path, "munic.png")
    library = { "display_name":None, "media":{}, "dirs":{}, "graphic_name":"munic.png", "graphic_filepath":graphic_filepath }
    # TODO Don't put empty stuff in, create ditionary entries when needed
    num_songs = 0
    num_graphics = 0
    unknown_extensions = []
    for media_dir in media_dirs:
        logging.info("Scanning media dir {}".format(media_dir))
        for path, dirs, files in os.walk(media_dir, followlinks=True):
            # Get files with music extensions, graphic extensions and unknown extensions
            music_files = [file for file in files if file.lower().endswith(known_music_formats) ]
            graphic_files = [file for file in files if file.lower().endswith(known_grapic_formats)]
            unknown_files = [file for file in files if file not in music_files and file not in graphic_files]

            if music_files or graphic_files:
                # 'path' is the full path to the files, e.g. /media/NAS_MEDIA/music/Queen/A Day At The Races"
                # Remove the root from the path to give the interesting part
                sub_path = path[len(media_dir):].lstrip("/").rstrip("/")

                # Ensure the dicts for this path exit in the library, and get the library dictionary into which the files should be added.
                # Simplify the name, so that near-duplicates (Guns'n'Roses, Guns N Roses) are treated as the same.
                parts = sub_path.split("/")
                base_dict = library
                for part in parts:
                    if part:    # (Directory might be empty meaning the root -- don't create a new dict for it!)
                        part_simplified = simplify(part)
                        if not part_simplified in base_dict["dirs"]:
                            base_dict["dirs"][part_simplified] = { "display_name":part, "media":{}, "dirs":{}, "graphic_name":None, "graphic_filepath":None }
                        base_dict = base_dict["dirs"][part_simplified]

                for music_file in music_files:
                    # Get the song name from the filename by stripping the extension
                    song_name = os.path.splitext(music_file)[0]
                    simplified_songname = simplify(song_name)
                    song_filepath = os.path.join(path, music_file)

                    # Insert the item, keyed by song name, with the full path as value
                    base_dict["media"][simplified_songname] = (song_name, song_filepath)

                    num_songs += 1

                largest_size = 0
                for graphic_filename in graphic_files:
                    graphic_filepath = os.path.join(path, graphic_filename)
                    size = os.path.getsize(graphic_filepath)
                    if size > largest_size:
                        base_dict["graphic_name"] = graphic_filename
                        base_dict["graphic_filepath"] = graphic_filepath
                        num_graphics += 1

            # Add the extensions of any unknown files to the unknown extensions list.
            # This gives the user a clue that they have unknown media types.
            for unknown_file in unknown_files:
                unknown_extension = os.path.splitext(unknown_file)[1]
                if unknown_extension not in unknown_extensions:
                    unknown_extensions.append(unknown_extension)

        logging.info("Loaded {} songs and {} graphics".format(num_songs, num_graphics))
        logging.info("Unknown media types: {}".format(unknown_extensions))

    return library

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(thread)d %(levelname)s %(funcName)s %(message)s')
    # TODO proper command-line parsing and help
    if len(sys.argv) < 2:
        logging.error("Specify one (or more) file lists")
        exit(-1)

    # Get the source directory
    script_path = os.path.dirname(os.path.realpath(__file__))

    # All arguments are media dirs
    media_dirs = sys.argv[1:]

    # Load the library of songs to serve
    library = load_library(media_dirs)

    # Serve on all interfaces, port 4444
    server = ThreadingSimpleServer(('0.0.0.0', 4444), Handler)

    # Delete any old transcode outputs. We do this after setting up the server so that if an instance is already running, we do not delete its transcodes.
    Transcoder.CleanUp()

    if USE_HTTPS:
        import ssl
        server.socket = ssl.wrap_socket(server.socket, keyfile='./key.pem', certfile='./cert.pem', server_side=True)
    logging.info("Serving on port 4444")
    server.serve_forever()

