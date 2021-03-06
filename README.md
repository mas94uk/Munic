# Munic
## Simple, small web-based music server and player
Munic is a very simple web-based music server and player.  The server is intended to run with minimal setup and consume minimal system resources (memory, disk space, CPU and network bandwidth).  It runs very comfortably on a Raspberry Pi Zero alongside nginx, PiHole and several other applications, or on my very under-powered Buffalo Linkstation LS220D even transcoding for a single user.

It presents your music in the structure it is stored on disk.  This makes it very fast to scan, but it relies on your music collection being organised nicely, for example named `Artist/Album/01 First Song.mp3`.

It will transcode music (to ogg or mp3, using ffmpeg) if your browser does not support the format it is stored in.

It does not read ID3 tags or other metadata.  Fuller-featured music servers/players are available if that is what you want: Airsonic and Ampache are good, for example.

## Screenshots
[![Front page](screenshots/Screenshot1.png)](screenshots/Screenshot1.png)
[![Album view](screenshots/Screenshot2.png)](screenshots/Screenshot2.png)

## Usage
Munic is tested on Ubuntu 20.04 and Debian Buster, but should work on any Linux with python3.  Let me know if you try it on other operating systems (Windows, Mac...).

1. Ensure you have ffmpeg installed (`sudo apt install ffmpeg`)
1. Clone or download the respository (`git clone ...` etc.)
2. `cd Munic`
3. `./music.py \path\to\your\music\library [\another\path\] [\yet\another\music\path]`
4. Browse to `http://localhost:4444`
5. The rest should be pretty obvious

## Current status
Munic is working and usable.  There are several more features I would like to implement -- see the todo list below.

## Todo list
- Store the equaliser settings between pages
- Add command-line config options: port, user:pass, or config file
- Add command-line help
- Document nginx reverse proxy setup
- Searching (server-side) and/or filtering of tracks
- m3a playlist support (including generating custom playlists)
- Change the header graphic to that of the currently-playing song
- Jump to entry on key input: register keydown hander, keep record (escape to clear). Show popup or similar with first match. Enter to follow.
- Repeat one song, repeat all songs, no repeat
- Remember volume setting (cookie?)

## Contributions
I am happy to accept contributions if they meet the goals of what I am trying to do - send me a message if you're not sure.  If they don't meet my goals, you are welcome to fork the project, of course.
