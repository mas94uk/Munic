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
import code # For code.interact()

# Whether to use HTTPS
USE_HTTPS = False

# Data structure containing the media library 
library = None

# Location of this sript
script_path = None

# Ongoing media GETs - for debug
media_gets = {}

# TODO: Transcoding
# 1. Can we send data slowly (with existing code or other)? Test, implement if possible.
# 2. Can we start playing a song before the whole thing is received? Test.
# 3. Put more sources in audio player: default + two others, named with id="..."
# 4. Python to offer multiple sources: the native format first and two alternatives (ogg and mp3)
# 5. Javascript to retrieve and set all three; player should auto choose the first it can play
# 6. Python to transcode on the fly if non-native format requested. Make sure it is killed if connection drops!

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
        # If path is a static file...
        # Bit hacky but ignoring the path means we do not have to worry about relative paths
        # TODO: Instead, put the right number of ../ in the link
        elif name.endswith("audioPlayer.js"):
            self.send_file(os.path.join(script_path, "audioPlayer.js"))
        # If the url ends with a "/", treat it as a playlist request for that location 
        elif name.endswith("/"):
            # Requesting a directory, which we treat as requesting a playlist for that location
            #   Queen/A Day At The Races/

            # Get the requested path and navigate to it.
            # As we go, build up "display_name" with the properly-formatted names of the directories
            requested_path = name.rstrip("/")
            logging.debug("Requested path: {}".format(requested_path))
            parts = requested_path.split("/")
            base_dict = library
            display_names = []
            dirs = base_dict["dirs"]
            # Remove empty parts which result from splitting empty strings etc.
            parts = [ part for part in parts if part]
            for part in parts:
                # If that directory does not exist
                if part not in dirs.keys():
                    logging.warn("Failed to find {} - failed at {}".format(requested_path, part))
                    self.send_response(404)
                    self.end_headers
                    return
                base_dict = dirs[part]
                display_names.append(base_dict["display_name"]) 
                dirs = base_dict["dirs"]

            # Read the playlist page template html from file
            with open("playlist.html") as html_file:
                html = html_file.read()

            # Construct the page. This will be all the directories directly under this one, as links,
            # and all the files from this directory onwards, as a playlist.

            # Get the headings: the display names of the path, or "Munic" if none
            if not display_names:
                display_names.append("Munic")

            # Lazy way to ensure there are enough items in the list to replace the headings
            display_names.append("")
            display_names.append("")

            # Drop in the headings
            for h in range(0,3):
                html = html.replace("__HEADING{}__".format(h), display_names[h])

            # Build the playlist links section
            playlist_links = ""
            if dirs:
                # Sort the keys (dir names) alphabetically
                dir_names = [ dir_name for dir_name in dirs.keys() ]
                dir_names.sort()
                for dir_name in dir_names:
                    display_name = dirs[dir_name]["display_name"]
                    link = dir_name + "/"
                    playlist_link = """<div><p><a href="__LINK__">__NAME__</a></p></div>""".replace("__LINK__", link).replace("__NAME__", display_name)
                    playlist_links = playlist_links + playlist_link

            # Drop the links into the html document
            html = html.replace("__PLAYLIST_LINKS__", playlist_links)

            # Build the playlist contents.  
            playlist_items = ""

            # Get all media files at or below this location
            media_items = get_media(base_dict)

            # Construct the list items
            for (song_display_name, song_constructed_filepath, song_filepath) in media_items:
                playlist_item = """<li><a href="__SONG_FILENAME__">__SONG_NAME__</a></li>\n""".replace("__SONG_FILENAME__", song_constructed_filepath).replace("__SONG_NAME__", song_display_name)
                playlist_items = playlist_items + playlist_item

            # Drop the playlist content into the html template
            html = html.replace("__PLAYLIST_ITEMS__", playlist_items)

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

            # Get the real media filename from the library by walking down the structure to the right directory
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
            basename = os.path.splitext(constructed_filename)[0]

            # Find the song in the dictionary (display name is key) and get its real filepath (the value)
            media = base_dict["media"]
            if basename not in media.keys():
                logging.warning("File {} not found in library".format(basename))
                self.send_response(404)
                self.end_headers()
                return
            filepath = media[basename]
            self.send_file(filepath, range_start, range_end)

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
    def send_file(self, localpath, range_start:int = None, range_end:int = None):
        logging.info("Sending file {}".format(localpath))
        media_gets[threading.get_ident()] = localpath

        # Was a range requested?
        range_requested = True if range_start is not None or range_end is not None else False

        # Get the mime type of the file
        mime_type, encoding = mimetypes.guess_type(localpath)

        with open(localpath, 'rb') as f:
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

            # If the requesed range was the entire file, do not send as a range.
            # This works around what appears to be a bug in Chrome and Chromium:
            # they request range 0-, but don't like to receive it as a range!
            if range_start==0 and range_end==file_length-1:
                logging.debug("Full range requested -> not sending as range")
                range_requested = False

            if range_requested:
                logging.info("Sending range {}-{}".format(range_start, range_end))
                content_length = 1 + range_end - range_start
                self.send_response(206) # Partial content
                self.send_header("Content-Range", "bytes={}-{}".format(range_start, range_end))
            else:
                logging.info("Sending entire file")
                content_length = file_length
                self.send_response(200)

            self.send_header("Accept-Ranges", 'bytes')
            self.send_header("Content-Length", content_length)
            if mime_type:
                self.send_header("Content-Type", mime_type)
            self.end_headers()

            try:
                # Seek to the desired start
                f.seek(range_start)

                # Read and send 16kB at a time
                while content_length > 0:
                    length_to_read = min(16384, content_length)
                    data = f.read(length_to_read)
                    length_read = len(data)
                    self.wfile.write(data)
                    content_length -= length_read

                logging.info("Successfully sent file {}".format(localpath))
            except BrokenPipeError:
                logging.warn("Broken pipe error sending {}".format(localpath))
            except ConnectionResetError:
                logging.warn("Connetion reset by peer sending {}".format(localpath))
        logging.info("File send finished on thread {}".format(threading.get_ident()))
        media_gets.pop(threading.get_ident())
        logging.debug("Ongoing transfers: " + str(media_gets)) 


class ThreadingSimpleServer(ThreadingMixIn, HTTPServer):
    pass

"""Return a simplified (searchable) version of the string, with all accents replaced with un-accented charaters,
all spaces and punctuation removed, and lower-case"""
def simplify(string):
    string = ''.join(c for c in unicodedata.normalize('NFD', string) if unicodedata.category(c) != 'Mn')
    string = ''.join([c for c in string if c.isalnum()])
    return string.lower()

""" Get a complete, flat list of all media in the library.
Returns an alphabetical list of tuples of (song display name, constructed filepath, media real filepath).
"Constructed filepath" is the apparent filepath relative to the given dir-dict, e.g. "Queen/A Day At The Races/Drowse.mp3".
(This includes the extension (e.g. .mp3) in case the browser requires it to play the file.)
Song display names are prefixed with subdir names if they are in sub-directories."""
def get_media(dir_dict, constructed_path: str = "", display_path: str = ""):
    media = dir_dict["media"]
    dirs = dir_dict["dirs"]

    result = []
    # Get all media files in this directory
    for media_display_name in media.keys():
        media_filepath = media[media_display_name]
        extension = os.path.splitext(media_filepath)[1]
        full_media_name = display_path.replace("/", ": ") + media_display_name
        constructed_filepath = constructed_path + media_display_name + extension 
        result.append( (full_media_name, constructed_filepath, media_filepath) )
    # Recurse into all sub-dirs, appending the directory name to the path
    for sub_dir in dirs.keys():
        sub_dir_dict = dirs[sub_dir]
        sub_dir_display_path = sub_dir_dict["display_name"]
        result = result + get_media(sub_dir_dict, constructed_path + sub_dir + "/", display_path + sub_dir_display_path + "/")

    # Sort alphabetially
    result.sort(key=lambda tup: tup[0].casefold())

    return result

# TODO Remove empty directories (may need to repeat until none are found as diretory may become empty if we remove its only subdir)
def load_library(media_dirs):
    # Walk the given path, creating a data structure as follows:
    # A recursive structure of a dict representing the top level, containing:
    #  - "display_name" (properly-formatted name, for display)
    #  - "media" (dict of songname:filename)
    #  - "dirs" (dict of simplified-dirname:directory-dict like the top level)
    #  - "graphic" (graphic filename, if present)
    # The filenames will be the full filepath of the file.
    # Directories will be indexed by "simplfied" name: a lower-case, alpha-numeric version of the real name.
    # Because we want to be able to overlay multiple directories, we cannot simply walk and create the structure as we find it.
    # Instead we check whether each directory exists and add it if not.
    # This has the desirable side-effects of merging directories with effectively the same name, and de-duplicating any songs
    # with identical artist/album/name.
    library = { "display_name":None, "media":{}, "dirs":{}, "graphic":None }
    # TODO Don't put empty stuff in, create ditionary entries when needed
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
                            base_dict["dirs"][part_simplified] = { "display_name":part, "media":{}, "dirs":{}, "graphic":None }
                        base_dict = base_dict["dirs"][part_simplified]

                for music_file in music_files:
                    # Get the song name from the filename by stripping the extension
                    song_name = os.path.splitext(music_file)[0]

                    # Insert the item, keyed by song name, with the full path as value
                    base_dict["media"][song_name] = path.rstrip("/") + "/" + music_file

                    num_songs += 1

                largest_size = 0
                for graphic_file in graphic_files:
                    graphic_filename = path.rstrip("/") + "/" + graphic_file
                    size = os.path.getsize(graphic_filename)
                    if size > largest_size:
                        base_dict["graphc"] = graphic_filename
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

    # Load the library of songs to serve
    library = load_library(sys.argv[1:])

    # Serve on all interfaces, port 4444
    server = ThreadingSimpleServer(('0.0.0.0', 4444), Handler)

    if USE_HTTPS:
        import ssl
        server.socket = ssl.wrap_socket(server.socket, keyfile='./key.pem', certfile='./cert.pem', server_side=True)
    server.serve_forever()

