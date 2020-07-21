# Munic
## Simple, small web-based music server and player
Munic is a very simple web-based music server and player.  It is intended to run with minimal setup and consume minimal system resources (memory, disk space, CPU and network bandwidth).  It runs very comfortably on a Raspberry Pi Zero, even alongside nginx, PiHole and several other applications.

It presents your music in the structure it is stored on disk.  This makes it very fast to scan, but it relies on your music collection being organised nicely, for example named `Artist/Album/01 First Song.mp3`.

It will transcode music (to ogg and mp3, using ffmpeg) if your browser does not support the format it is stored in.

It does not read ID3 tags or other metadata.  Fuller-featured music servers/players are available if that is what you want: Airsonic and Ampache are good, for example.

## Usage
Munic is tested on Ubuntu 18.04 but should work on any Linux with python3.  Let me know if you try it on other operating systems (Windows, Mac...).

1. Clone or download the respository (`git clone ...` etc.)
2. `cd Munic`
3. `./music.py \path\to\your\music\library [\another\path\] [\yet\another\music\path]`
4. Browse to `http://localhost:4444`
5. The rest should be pretty obvious

## Current status
Munic is currently working, but needs finesse.

## Todo list
- Prettify the client: use a custom player rather than brower's built in one
- Add support for simple HTTP authentication
- Add ability to rescan library (currently just restart it to do this)
- Add command line help

## Contributions
I am happy to accept contributions if they meet the goals of what I am trying to do - send me a message if you're not sure.  If they don't meet my goals, you are welcome to fork the project, of course.
