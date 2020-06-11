#!/usr/bin/python3

# Munic - simple web-based music server

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import threading
from urllib import parse as urllibparse
import shutil
import sys
import os
import code # For code.interact()

# Whether to use HTTPS
USE_HTTPS = False

# Data structure containing the media library 
library = None

# Location of this sript
script_path = None

# TODO: Transcoding
# 1. Can we send data slowly (with existing code or other)? Test, implement if possible.
# 2. Can we start playing a song before the whole thing is received? Test.
# 3. Put more sources in audio player: default + two others, named with id="..."
# 4. Python to offer multiple sources: the native format first and two alternatives (ogg and mp3)
# 5. Javascript to retrieve and set all three; player should auto choose the first it can play
# 6. Python to transcode on the fly if non-native format requested. Make sure it is killed if connection drops!

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        print("path: {}\n".format(self.path))
        name = self.path
        # name = name.lstrip("/")
        name = urllibparse.unquote(name)
        print("name: {}\n".format(name))

        # Front page
        if name == "":
            # TODO special case for front page
            self.send_response(200)
            self.end_headers()
            self.wfile.write("Coming soon".encode("utf-8"))
        # If path is a static file...
        # Bit hacky but ignoring the path means we do not have to worry about relative paths
        elif name.endswith("audioPlayer.js"):
            self.send_response(200)
            self.end_headers()
            self.send_file(os.path.join(script_path, "audioPlayer.js"))
        # If the url ends with a "/", treat it as a playlist request for that location 
        elif name.endswith("/"):
            # Requesting a directory, which we treat as requesting a playlist for that location
            #   Queen/A Day At The Races/

            # Get the requested path and navigate to it 
            requested_path = name.rstrip("/")
            print("Requested path: {}".format(requested_path))
            parts = requested_path.split("/")
            base_dict = library
            dirs = base_dict["dirs"]
            # Remove empty parts which result from splitting empty strings etc.
            parts = [ part for part in parts if part]
            for part in parts:
                print("Part {}".format(part))
                # If that directory does not exist
                if part not in dirs.keys():
                    print("Failed to find {} - failed at {}".format(requested_path, part))
                    self.send_response(404)
                    self.end_headers
                    return
                base_dict = dirs[part]
                dirs = base_dict["dirs"]

            # Requested path is known to be available now, so send response
            self.send_response(200)
            self.end_headers()

            # Read the playlist page template html from file
            with open("playlist.html") as html_file:
                html = html_file.read()

            # Construct the page. This will be all the directories directly under this one, as links,
            # and all the files from this directory onwards, as a playlist.

            # Get the headings: parts of the path, or "Munic" if none
            if len(parts) == 0:
                parts.append("Munic")
            parts.append("")
            parts.append("")
            for h in range(0,3):
                html = html.replace("__HEADING{}__".format(h), parts[h])

            # Build the song links section
            playlist_links = ""
            if dirs:
                # Sort the keys (dir names) alphabetically
                dir_names = [ dir_name for dir_name in dirs.keys() ]
                dir_names.sort(key=str.casefold)
                for dir_name in dir_names:
                    link = dir_name + "/"
                    playlist_link = """<p><a href="__LINK__">__NAME__</a></p>""".replace("__LINK__", link).replace("__NAME__", dir_name)
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

            self.wfile.write(html.encode("utf-8"))

        # Otherwise, assume the request is for a media file 
        else:
            print("Attempting to get file {}".format(name))

            # Get the real media filename from the library by walking down the structure to the right directory
            parts = name.lstrip("/").split("/")
            base_dict = library
            for dir_part in parts[:-1]:
                dirs = base_dict["dirs"]
                if dir_part not in dirs.keys():
                    print("Requested unknown file: {} - failed at {}".format(name, dir_part))
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
                print("File {} not found in directory".format(basename))
                self.send_response(404)
                self.end_headers()
                return
            filepath = media[basename]
            print("Sending file {}".format(filepath))
            self.send_response(200)
            self.end_headers()
            self.send_file(filepath)

    def send_html(self, htmlstr):
        "Simply returns htmlstr with the appropriate content-type/status."
        # self.send_resp_headers(200, {'Content-type': 'text/html; charset=utf-8'}, end=True)
        self.wfile.write(htmlstr.encode("utf-8"))

    def send_file(self, localpath):
        "Does what it says on the tin! Includes correct content-type/length."
        with open(localpath, 'rb') as f:
            # self.send_resp_headers(200,
            #                        {'Content-length': os.fstat(f.fileno())[6],
            #                         'Content-type': mimetypes.guess_type(localpath)[0]},
            #                        end=True)
            shutil.copyfileobj(f, self.wfile)


class ThreadingSimpleServer(ThreadingMixIn, HTTPServer):
    pass


def run():
    # Serve on all interfaces, port 4444
    server = ThreadingSimpleServer(('0.0.0.0', 4444), Handler)
    if USE_HTTPS:
        import ssl
        server.socket = ssl.wrap_socket(server.socket, keyfile='./key.pem', certfile='./cert.pem', server_side=True)
    server.serve_forever()

""" Get a complete, flat list of all media in the library.
Returns an alphabetical list of tuples of (song display name, constructed filepath, media real filepath).
"Constructed filepath" is the apparent filepath relative to the given dir-dict, e.g. "Queen/A Day At The Races/Drowse.mp3".
(This includes the extension (e.g. .mp3) in case the browser requires it to play the file.)
Song display names are prefixed with subdir names if they are in sub-directories."""
def get_media(dir_dict, path: str = ""):
    media = dir_dict["media"]
    dirs = dir_dict["dirs"]

    result = []
    # Get all media files in this directory
    for media_display_name in media.keys():
        media_filepath = media[media_display_name]
        extension = os.path.splitext(media_filepath)[1]
        full_media_name = path.replace("/", ": ") + media_display_name
        constructed_filepath = path + media_display_name + extension 
        result.append( (full_media_name, constructed_filepath, media_filepath) )
    # Recurse into all sub-dirs, appending the directory name to the path
    for sub_dir in dirs.keys():
        result = result + get_media(dirs[sub_dir], path + sub_dir + "/")

    # Sort alphabetially
    result.sort(key=lambda tup: tup[0].casefold())

    return result

# TODO Remove empty directories (may need to repeat until none are found as diretory may become empty if we remove its only subdir)
def load_library(media_dirs):
    # Walk the given path, creating a data structure as follows:
    # A recursive structure of a dict representing the top level, containing:
    #  - "media" (dict of songname:filename)
    #  - "dirs" (dict of dirname:directory-dict like the top level)
    #  - "graphic" (graphic filename, if present)
    # The filenames will be the full filepath of the file.
    # Because we want to be able to overlay multiple directories, we cannot simply walk and create the structure as we find it.
    # Instead we check whether each directory exists and add it if not.
    # This will have the free side-effect of de-duplicating any songs with identical artist/album/name.
    library = { "media":{}, "dirs":{}, "graphic":None }
    num_songs = 0
    num_graphics = 0
    for media_dir in media_dirs:
        print("Scanning media dir {}".format(media_dir))
        for path, dirs, files in os.walk(media_dir):
            # We are only interested in files with music extensions
            music_files = [file for file in files if file.lower().endswith((".mp3", ".m4a", ".ogg", ".wav", ".flac", ".wma")) ]

            graphic_files = [file for file in files if file.lower().endswith((".jpg", ".jpeg", ".gif", ".bmp", ".png"))]

            if music_files or graphic_files:
                # 'path' is the full path to the files, e.g. /media/NAS_MEDIA/music/Queen/A Day At The Races"
                # Remove the root from the path to give the interesting part
                sub_path = path[len(media_dir):].lstrip("/").rstrip("/")

                # Ensure the dicts for this path exit in the library, and get the library dictionary into which the files should be added
                parts = sub_path.split("/")
                base_dict = library
                for part in parts:
                    if not part in base_dict["dirs"]:
                        base_dict["dirs"][part] = { "media":{}, "dirs":{}, "graphic":None }
                    base_dict = base_dict["dirs"][part]

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

        print("Loaded {} songs and {} graphics".format(num_songs, num_graphics))

    return library

if __name__ == '__main__':
    # TODO proper command-line parsing and help
    if len(sys.argv) < 2:
        print("Specify one (or more) file lists")
        exit(-1)

    # Get the source directory
    script_path = os.path.dirname(os.path.realpath(__file__))

    # Load the library of songs to serve
    library = load_library(sys.argv[1:])
    # code.interact(local=locals())


    run()
