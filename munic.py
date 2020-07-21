#!/usr/bin/python3

# Munic - simple web-based music server

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import threading
from urllib import parse as urllibparse
import sys
import os
import unicodedata
import mimetypes
import logging
import re
import random
import subprocess
import time
import code # For code.interact()

# Whether to use HTTPS
USE_HTTPS = False

# Maximum number of simultaneous transcodes to allow (or 0 to not allow transcoding)
MAX_SIMULTANEOUS_TRANSCODES = 2

# Maximum number of completed transcodes to preserve
MAX_COMPLETED_TRANSCODES = 20

# Data structure containing the media library 
library = None

# Location of this sript
script_path = None

# Ongoing media GETs - for debug
media_gets = {}

# Start with an empty list of transcode jobs
transcoders = []

class Transcoder:
    # Index for the next transcode temp file
    nextIndex = 0

    """ Constructor """
    def __init__(self, requested_filepath, source_filepath, target_extension):
        self.finished = False
        self.requested_filepath = requested_filepath

        out_file = "TRANSCODE_{}{}".format(Transcoder.nextIndex, target_extension)
        Transcoder.nextIndex += 1

        logging.info("Creating transcode session for {} -> {} (Temp file: {})".format(source_filepath, target_extension, out_file))

        # TODO use a proper temp directory
        self.out_file = os.path.join(script_path, out_file)

        # Delete the file if it exists (probably left over from a previous session)
        if os.path.exists(self.out_file):
            os.remove(self.out_file)

        # Start the transcode
        self.transcode_process = subprocess.Popen(["ffmpeg", "-i", source_filepath, self.out_file],
                                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    """ Destructor """
    def __del__(self):
        # Stop the active transcode
        if not self.transcode_finished():
            self.transcode_process.kill()

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

        # If we are still transcoding, wait up to 5s for the file to appear
        for i in range(0,50):
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
        logging.info("GET path: {} on thread {}\n".format(self.path, threading.get_ident()))

        name = self.path
        name = urllibparse.unquote(name)

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
        # If the url ends with a "/" or "/*", treat it as a menu/playlist request for that location 
        elif name.endswith("/") or name.endswith("/*"):
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
                    logging.warn("Failed to find {} - failed at {}".format(requested_path, part))
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

            # Drop in the root location
            html = html.replace("__ROOT__", root)

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
            r = [ random.randint(1,3) for a in range (0,9) ]
            colours = [ "#{}{}{}".format(r.pop(), r.pop(), r.pop()) for a in range(0,3) ]
            for c in range(0,3):
                html = html.replace("__COL{}__".format(c), colours[c])

            # Build the playlist (subdir) links section
            playlist_links = ""
            # If we are not showing the songs in the folder, the first link is always "All songs"
            if not include_songs:
                playlist_links = """<div class="speciallink"><p><a href="*">All Songs</a></p></div>"""

            if dirs:
                # Sort the keys (dir names) alphabetically
                # Note that we are sorting by "simplified name", so "The Beatles" is in with the Bs, not the Ts.
                dir_names = [ dir_name for dir_name in dirs.keys() ]
                dir_names.sort()
                for dir_name in dir_names:
                    display_name = dirs[dir_name]["display_name"]
                    link = dir_name + "/*"  # Include '*' to take us to the playlist
                    playlist_link = """<div class="playlistlink"><p><a href="__LINK__">__NAME__</a></p></div>""".replace("__LINK__", link).replace("__NAME__", display_name)
                    playlist_links = playlist_links + playlist_link

            # Drop the links into the html document
            html = html.replace("__PLAYLIST_LINKS__", playlist_links)

            # Build the playlist contents.  
            playlist_items = ""

            if include_songs:
                # Get all media files at or below this location
                media_items = get_all_songs(base_dict)

                # Construct the list items
                for (song_display_name, song_constructed_filepath) in media_items:
                    playlist_item = """<li><a href="__SONG_FILENAME__">__SONG_NAME__</a></li>\n""".replace("__SONG_FILENAME__", song_constructed_filepath).replace("__SONG_NAME__", song_display_name)
                    playlist_items = playlist_items + playlist_item

            # Drop the playlist content into the html template
            html = html.replace("__PLAYLIST_ITEMS__", playlist_items)

            # Find album art
            album_art = None
            # If there is a graphic at this level, use it
            if base_dict["graphic"]:
                album_art = base_dict["graphic"]
            # Otherwise get a random image from anywhere below this
            else:
                album_arts = get_all_graphics(base_dict)
                logging.debug("Found {} graphics to choose from".format(len(album_arts)))

                if album_arts:
                    album_art = random.choice(album_arts)

            # If no graphic found, use the default logo
            if not album_art:
                album_art = root + "munic.png"

            # Drop in the album art
            html = html.replace("__ALBUMART__", album_art);
            self.send_html(html)

        # Otherwise, assume the request is for a media file 
        else:
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
            if constructed_filename == base_dict["graphic"]:
                filepath = base_dict["path"] + base_dict["graphic"]
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
                        self.send_transcoded_file(name, filepath, requested_extension)
                        found = True
            
            if not found:
                logging.warning("File {}{}) not found in library".format(basename, requested_extension))
                self.send_response(404)
                self.end_headers()
                return

        logging.info("GET completed")

    def send_html(self, htmlstr):
        "Simply sends htmlstr with status 200 and the correct content-type and content-length."

        # Encode the HTML
        encoded = htmlstr.encode("utf-8")
        logging.info("Sending HTML ({} bytes)".format(len(encoded)))

        self.send_response(200)
        self.send_header("Content-Length", len(encoded))
        self.send_header("Content-Type", 'text/html; charset=utf-8')
        self.send_header("Accept-Ranges", 'bytes')
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
            # If the file is not seekable, end the whole thing.
            # (We could read and discard if this is a problem, but it is not expected to happen.)
            if range_requested and not f.seekable():
                logging.warn("File not seekable: not sending range")
                range_requested = False
                range_start = None
                range_end = None

            # Find the length of the file
            file_length = os.fstat(f.fileno())[6]
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
                logging.warn("Broken pipe error sending {} after {} bytes".format(filepath, total_sent))
            except ConnectionResetError:
                logging.warn("Connetion reset by peer sending {} after {} bytes".format(filepath, total_sent))
        logging.info("File send finished on thread {}".format(threading.get_ident()))
        media_gets.pop(threading.get_ident())
        logging.debug("Ongoing transfers: " + str(media_gets)) 

    """ Send the given file, transcoded to the specified format"""
    def send_transcoded_file(self, requested_filepath, source_filepath, requested_extension):
        logging.info("Sending transcoded file {} -> {}".format(source_filepath, requested_filepath))
        # TODO Add range support for transcoded files

        # Get the existing transcoder if it exists
        transcoder = None
        for t in transcoders:
            if t.requested_filepath == requested_filepath:
                transcoder = t

                # 'Refresh' this transcoder by moving it to the end of the list
                transcoders.remove(t)
                transcoders.append(t)
                break

        # Else create a new one and store it
        if not transcoder:
            transcoder = Transcoder(requested_filepath, source_filepath, requested_extension)
            transcoders.append(transcoder)

        # Housekeep existing transcoders:
        # Get a list of still-in-progress transcoders
        running = [t for t in transcoders if not t.transcode_finished()]
        # Remove the oldest running transcoders
        while len(running) > MAX_SIMULTANEOUS_TRANSCODES:
            logging.info("Removing one running transcoder")
            t = running.pop(0)
            transcoders.remove(t)

        # Get a list of completed transcodes
        completed = [t for t in transcoders if t.transcode_finished()]
        # Remove the oldest completed transcodes
        while len(transcoders) > MAX_COMPLETED_TRANSCODES:
            logging.info("Removing one completed transcode")
            t = completed.pop(0)
            transcoders.remove(t)

        # Get the mime type of the transcoded file
        mime_type, encoding = mimetypes.guess_type(requested_filepath)

        # Get the name of the transcoded file (also waits for it to be created)
        transcoded_filepath = transcoder.get_transcoded_filepath()

        # If the file was not created, send a 404.  Note that it could just be very slow.
        if not transcoded_filepath:
            self.send_response(404)
            self.end_headers
            return

        self.send_response(200)
        self.send_header("Accept-Ranges", 'bytes')
        self.send_header("Cache-Control", "max-age=1000")
        if mime_type:
            self.send_header("Content-Type", "audio/ogg")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        total_sent = 0
        CHUNK_SIZE = 65536  # 64kB at a time
        time.sleep(1)
        try:
            with open(transcoded_filepath, 'rb') as f:
                # While we are still transcoding, send 16kB at a time
                while True:
                    file_length = os.fstat(f.fileno())[6]
                    if file_length >= total_sent + CHUNK_SIZE:
                        data = f.read(CHUNK_SIZE)
                        length_read = len(data)
                        chunk_size_string = "%x\r\n" % length_read
                        self.wfile.write(chunk_size_string.encode("utf-8"))
                        self.wfile.write(data)
                        self.wfile.write("\r\n".encode("utf-8"))
                        total_sent += length_read
                    else:
                        time.sleep(0.1)

                    # If the transcoding has finished...
                    if transcoder.transcode_finished():
                        # ...exit the loop
                        break

                # Send the rest
                logging.info("Transcoding complete; sending the rest")
                file_length = os.fstat(f.fileno())[6]
                while total_sent < file_length:
                    remaining = file_length - total_sent
                    length_to_read = min(CHUNK_SIZE, remaining)
                    data = f.read(length_to_read)
                    length_read = len(data)
                    chunk_size_string = "%x\r\n" % length_read
                    self.wfile.write(chunk_size_string.encode("utf-8"))
                    self.wfile.write(data)
                    self.wfile.write("\r\n".encode("utf-8"))
                    total_sent += length_read

                # Send an empty chunk to indicate the end of file
                self.wfile.write("0\r\n\r\n".encode("utf-8"))

                logging.info("Successfully sent transcoded file ({} bytes)".format(total_sent))
        except BrokenPipeError:
            logging.warn("Broken pipe error sending {} after {} bytes".format(requested_filepath, total_sent))
        except ConnectionResetError:
            logging.warn("Connetion reset by peer sending {} after {} bytes".format(requested_filepath, total_sent))

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
Returns an alphabetical list of tuples of (song display name, constructed filepath).
"Constructed filepath" is the apparent filepath relative to the given dir-dict, e.g. "Queen/A Day At The Races/Drowse.mp3".
(This includes the extension (e.g. .mp3) in case the browser requires it to play the file.)
Song display names are postfixed with subdir names if they are in sub-directories, e.g. "Tie Your Mother Down (Queen: A Day At The Races)"."""
def get_all_songs(dir_dict, constructed_path: str = "", display_path: str = ""):
    media = dir_dict["media"]
    dirs = dir_dict["dirs"]

    results = []
    # Get all media files in this directory, sorted alphabetically
    for media_simplified_name in media.keys():
        media_filepath = media[media_simplified_name][1]
        extension = os.path.splitext(media_filepath)[1]
        constructed_filepath = constructed_path + media_simplified_name + extension 
        media_display_name = media[media_simplified_name][0]
        
        # If there is a path, add it on the end (suitably formatted)
        formatted_display_path = display_path.rstrip("/").replace("/", ": ")
        if formatted_display_path:
            media_display_name += " ({})".format(formatted_display_path)
        results.append( (media_display_name, constructed_filepath) )
        results.sort(key=lambda tup: tup[0].casefold())

    # Recurse into all sub-dirs (in alphabetical order), appending the directory name to the path
    sub_dirs = [sd for sd in dirs.keys()]
    sub_dirs.sort()
    for sub_dir in sub_dirs:
        sub_dir_dict = dirs[sub_dir]
        sub_dir_display_path = sub_dir_dict["display_name"]
        results = results + get_all_songs(sub_dir_dict, constructed_path + sub_dir + "/", display_path + sub_dir_display_path + "/")

    return results

""" Get a complete, flat list of all graphics in the library.
Returns a list of constructed filepaths.
"Constructed filepath" is the apparent filepath relative to the given dir-dict, e.g. "Queen/A Day At The Races/folder.jpg".
(This includes the extension (e.g. .jpg).)"""
def get_all_graphics(dir_dict, constructed_path: str = "", display_path: str = ""):
    dirs = dir_dict["dirs"]

    result = []

    # Get graphic file in this directory, if it exists
    if dir_dict["graphic"]:
        result.append(constructed_path + dir_dict["graphic"])

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
    #  - "path" (the path to the real location of this directory, ending with "/")
    #  - "media" (dict of simplified-songname:tuple of (songname:filepath) )
    #  - "dirs" (dict of simplified-dirname:directory-dict like the top level)
    #  - "graphic" (graphic filename, if present)
    # The filenames will be the full filepath of the file.
    # Directories will be indexed by "simplfied" name: a lower-case, alpha-numeric version of the real name, with the first "the" removed.
    # Because we want to be able to overlay multiple directories, we cannot simply walk and create the structure as we find it.
    # Instead we check whether each directory exists and add it if not.
    # This has the desirable side-effects of merging directories with effectively the same name, and de-duplicating any songs
    # with identical artist/album/name.
    # The location of the bottom level will be that of the script, so that the default graphic can be found.
    library = { "display_name":None, "path":script_path +"/", "media":{}, "dirs":{}, "graphic":"munic.png" }
    # TODO Don't put empty stuff in, create ditionary entries when needed
    # TODO There's a bug here: if the same album exists in two locations, we merge them but only store one path.
    #      Hence half the links are broken -- most noticeable with the graphics.
    #      Probably revert to storing the whole filepath, for seamless merging. 
    num_songs = 0
    num_graphics = 0
    for media_dir in media_dirs:
        logging.info("Scanning media dir {}".format(media_dir))
        for path, dirs, files in os.walk(media_dir):
            # We are only interested in files with music extensions
            music_files = [file for file in files if file.lower().endswith((".mp3", ".m4a", ".ogg", ".wav", ".flac", ".wma")) ]

            graphic_files = [file for file in files if file.lower().endswith((".jpg", ".jpeg", ".gif", ".bmp", ".png"))]

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
                            base_dict["dirs"][part_simplified] = { "display_name":part, "path":path.rstrip("/") + "/", "media":{}, "dirs":{}, "graphic":None }
                        base_dict = base_dict["dirs"][part_simplified]

                for music_file in music_files:
                    # Get the song name from the filename by stripping the extension
                    song_name = os.path.splitext(music_file)[0]
                    simplified_songname = simplify(song_name)
                    song_filepath = path.rstrip("/") + "/" + music_file

                    # Insert the item, keyed by song name, with the full path as value
                    base_dict["media"][simplified_songname] = (song_name, song_filepath)

                    num_songs += 1

                largest_size = 0
                for graphic_file in graphic_files:
                    graphic_filename = path.rstrip("/") + "/" + graphic_file
                    size = os.path.getsize(graphic_filename)
                    if size > largest_size:
                        base_dict["graphic"] = graphic_file
                        num_graphics += 1

        logging.info("Loaded {} songs and {} graphics".format(num_songs, num_graphics))

    return library

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(thread)d %(levelname)s %(funcName)s %(message)s')
    # TODO proper command-line parsing and help
    if len(sys.argv) < 2:
        logging.error("Specify one (or more) file lists")
        exit(-1)

    # Get the source directory
    script_path = os.path.dirname(os.path.realpath(__file__))

    # TODO Delete any old transcode outputs

    # Load the library of songs to serve
    library = load_library(sys.argv[1:])

    # Serve on all interfaces, port 4444
    server = ThreadingSimpleServer(('0.0.0.0', 4444), Handler)

    if USE_HTTPS:
        import ssl
        server.socket = ssl.wrap_socket(server.socket, keyfile='./key.pem', certfile='./cert.pem', server_side=True)
    server.serve_forever()

