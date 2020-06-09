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

USE_HTTPS = False

library = None

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        print("path: {}\n".format(self.path))
        name = self.path
        name = name.strip("/")
        name = urllibparse.unquote(name)
        print("name: {}\n".format(name))

        # If path is a filepath of a file we know about...
        if name.startswith("media/"):
            # Ensure the song is in the library, to prevent someone from getting arbitrary paths -> security hazard
            all_media = get_media(library)
            song_filenames = [ media[1] for media in all_media ]

            requested_filename = name[len("media/"):]
            if requested_filename in song_filenames:
                self.send_response(200)
                self.end_headers()
                self.send_file(requested_filename)
            else:
                print("Requested unknown file: {}".format(requested_filename))
                self.send_response(404)
                self.end_headers()
        elif name == "audioPlayer.js":
            # TODO sort path
            self.send_response(200)
            self.end_headers()
            self.send_file("/home/mark/Development/Munic/audioPlayer.js")
        elif name == "":
            # TODO special case for front page
            self.send_response(200)
            self.end_headers()
            self.wfile.write("Coming soon".encode("utf-8"))
        elif name.startswith("playlist"):
            self.send_response(200)
            self.end_headers()
            # Requesting a playlist
            #   playlist/Queen/A Day At The Races

            # Read the playlist page template html from file
            with open("index.html") as html_file:
                html = html_file.read()

            # Get the requested path and navigate to it 
            requested_path = name[len("playlist"):].strip("/")
            print("Requested path: {}".format(requested_path))
            parts = requested_path.split("/")
            base_dict = library
            dirs = base_dict["dirs"]
            for part in parts:
                # If the path part is non-empty
                if part:
                    print("Part {}".format(part))
                    # If that directory does not exist
                    if part not in dirs.keys():
                        print("not found")
                        self.send_response(404)
                        self.end_headers
                        return
                    print("found")
                    base_dict = dirs[part]
                    dirs = base_dict["dirs"]

            # Construct the page. This will be all the directories directly under this one, as links,
            # and all the files from this directory onwards, as a playlist.

            # TODO: Header - perhaps the requested path with /s replaced with <p/> and progressively smaller fonts?

            # Build the links section
            playlist_links = ""
            if dirs:
                for dir_name in dirs.keys():
                    link = "/playlist/" + requested_path + "/" + dir_name
                    playlist_link = """<p><a href="__LINK__">__NAME__</a></p>""".replace("__LINK__", link).replace("__NAME__", dir_name)
                    playlist_links = playlist_links + playlist_link

            # Drop the links into the html document
            html = html.replace("__PLAYLIST_LINKS__", playlist_links)

            # Build the playlist contents.  
            playlist_items = ""

            # Get all media files at or below this location
            media_items = get_media(base_dict)

            for (song_name, song_filename) in media_items:
                # Prefix song_filename with "/media/" so that we can detect it above
                song_filename = "/media/" + song_filename
                playlist_item = """<li><a href="__SONG_FILENAME__">__SONG_NAME__</a></li>\n""".replace("__SONG_FILENAME__", song_filename).replace("__SONG_NAME__", song_name)
                playlist_items = playlist_items + playlist_item


            # for song_filename in music_filenames:
            #     # Get the song title from the filepath-- the filename, wuthout the extension
            #     parts = song_filename.split("/")
            #     filename = parts[-1]
            #     parts = filename.split(".")
            #     song_name = parts[0]

            #     playlist_item = """<li><a href="__SONG_FILENAME__">__SONG_NAME__</a></li>\n""".replace("__SONG_FILENAME__", song_filename).replace("__SONG_NAME__", song_name)
            #     playlist_items = playlist_items + playlist_item

            # Drop the playlist content into the html template
            html = html.replace("__PLAYLIST_ITEMS__", playlist_items)


            self.wfile.write(html.encode("utf-8"))

            # songs_html = ""
            # for music_filename in music_filenames:
            #     # Get the song title from the filepath-- the filename, wuthout the extension
            #     parts = music_filename.split("/")
            #     filename = parts[-1]
            #     parts = filename.split(".")
            #     song_title = parts[0]

            #     # Generate HTML to present a player for this song
            #     song_html = """<p><audio controls><source src="__FILE__" type="audio/mpeg">Your browser does not support the audio element.</audio>__TITLE__</p>"""
            #     song_html = song_html.replace("__FILE__", music_filename).replace("__TITLE__", song_title)
            #     songs_html += song_html

            #     # TODO: This basically works, but the brower loads EVERY mp3 in advance.
            #     # TODO: We need to put a playlist in so it loads them as needed

            # self.wfile.write(songs_html.encode("utf-8"))
        else:
            # Not expeted: do nothing
            print("File {} not supported - returning nothing".format(name))
            pass

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
Returns a list of tuples of (song name, media filename).
Song names are prefixed with subdir names if they are in sub-directories."""
def get_media(dir_dict, prefix: str = ""):
    media = dir_dict["media"]
    dirs = dir_dict["dirs"]

    result = []
    for media_name in media.keys():
        full_media_name = prefix + media_name
        media_filename = media[media_name]
        result.append( (full_media_name, media_filename) )
    for sub_dir in dirs.keys():
        result = result + get_media(dirs[sub_dir], prefix + sub_dir+": ")

    return result

def load_library(media_dirs):
    # Walk the given path, creating a data structure as follows:
    # A recursive structure of a dict representing the top level, containing:
    #  - "media" (dict of filename strings)
    #  - "dirs" (dict of dicts like the top level)
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
    if len(sys.argv) < 2:
        print("Specify one (or more) file lists")
        exit(-1)

    # Load the library of songs to serve
    library = load_library(sys.argv[1:])
    # code.interact(local=locals())

    # TODO: Need to think about how to structure them and how to sensibly create playlists

    # Temp hack: Load a list of files to serve, from the supplied files
    # music_filenames = []
    # for file_list_file in sys.argv[1:]:
    #     with open(file_list_file) as music_filenames_file:
    #         new_music_filenames = music_filenames_file.readlines()
    #         new_music_filenames = [ music_filename.strip() for music_filename in new_music_filenames ]
    #         print("Read {} files from {}".format(len(new_music_filenames), file_list_file))
    #         music_filenames = music_filenames + new_music_filenames
    # print("Read {} files".format(len(music_filenames)))
    run()
