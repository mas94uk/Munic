/* Javascript audio player */

class AudioPlaylist{
    onPlay(){
        // Connect the player output to the equaliser input
        this.init();
        this.muneq.setInput(this.activeMediaSource);

        // Set the title and now-playing.
        // We do this here, rather than in setTrack(), so that it does not happen when the
        // page loads and nothing is yet playing.
        var listPos = this.trackOrder[this.trackPos]; // to account for shuffle mode
        var listItem = this.playlist.children[listPos];
        var link = listItem.getElementsByTagName("a")[0];
        var songTitle = listItem.getElementsByTagName("p")[0].textContent.trim();

        // Try to get the album name. If we have a second 'p' in the link, use it.
        // Otherwise take the h2 value. This is a bit hacky but works in most cases.
        var songAlbum = listItem.getElementsByTagName("p")[1].textContent.trim();
        var playlistAlbum = this.header2.textContent.trim();
        var album = songAlbum.length>0 ? songAlbum : playlistAlbum;

        var nowPlaying = songTitle;
        if (album.length > 0)
            nowPlaying = nowPlaying + " (" + album + ")";
        this.nowPlaying.textContent  = nowPlaying;
        this.title.textContent = songTitle;

        // Highlight the currently-playing track
        link.classList.add(this.currentClass);

        // Move the link to the middle of the screen
        link.scrollIntoView({ behavior: "smooth", block: "center", inline: "center"});

        // Set the mediasession metadata (for integration on phones etc.)
        // This is a bit of a guess since we don't really know the artist and album, but we will assume they
        // are the first and second level titles.
        var image = this.playlist.getElementsByTagName("img")[listPos]; // Song image
        var dims = image.naturalWidth + "x" + image.naturalHeight;
        var artwork = [{ src: image.src, sizes: dims, type: image.mimeType}];
        var meta = new MediaMetadata();
        meta.title = songTitle;
        meta.artist = this.header1.textContent;
        meta.album = album;
        meta.artwork = artwork;
        navigator.mediaSession.metadata = meta;
    }

    randomizeOrder(length){
        var trackOrder = this.defaultOrder(length);
        for (var i = trackOrder.length - 1; i > 0; i--) {
            var j = Math.floor(Math.random() * (i + 1));
            var temp = trackOrder[i];
            trackOrder[i] = trackOrder[j];
            trackOrder[j] = temp;
        }
        return trackOrder;
    }

    defaultOrder(length) {
        // Empty track array, fill array with indices in order
        var trackOrder = [];
        for(var i = 0; i < length; i++){
            trackOrder.push(i);
        }
        return trackOrder;     
    }

    getSources(listPos) {
        var original_url = this.playlist.getElementsByTagName("li")[listPos].getElementsByTagName("a")[0].href;

        // Split the extension (.mp3 etc.) off
        var dotPos = original_url.lastIndexOf('.');
        var stem = original_url.substring(0, dotPos);
        var original_format = original_url.substring(dotPos + 1);
        
        // Generate a list of sources: the original, and transcoded alternatives
        // TODO: Only offer alternate formats if the back end offers transcoding.
        var source_template = '<source src="__FILE__" type="audio/__MIMETYPE__">';
        var sources = "";

        // Put the original format first, except if it is FLAC or WAV (because the bandwidth use is too high)
        if(original_format != "flac" && original_format != "wav") {
            sources = sources + source_template.replace("__FILE__", original_url).replace("__MIMETYPE__", this.mimeType(original_format));
        }
        // Offer ogg transcode (if the original was not ogg)
        if(original_format != "ogg") {
            sources = sources + source_template.replace("__FILE__", stem + ".ogg").replace("__MIMETYPE__", "ogg");
        }
        // Offer mp3 transcode (if the original was not mp3)
        if(original_format != "mp3") {
            sources = sources + source_template.replace("__FILE__", stem + ".mp3").replace("__MIMETYPE__", "mpeg");
        }

        return sources;
    }

    setTrack(arrayPos){
        console.log("setTrack " + arrayPos);

        // Remove the highlight
        var currents = document.getElementsByClassName(this.currentClass);
        for(var i=0 ; i<currents.length ; ++i) {
            currents[i].classList.remove(this.currentClass);
        }

        // Remove the metadata for the previously playing track
        navigator.mediaSession.metadata = null;

        // If the spare player is already loaded with the requested track
        if(arrayPos == this.sparePlayerTrackPos) {
            // Stop the current player
            this.activePlayer.pause();
            this.activePlayer.innerHTML = "";

            // Make the spare player the active one and the active one the spare
            var temp = this.activePlayer;
            this.activePlayer = this.sparePlayer;
            this.sparePlayer = temp;

            temp = this.activeMediaSource;
            this.activeMediaSource = this.spareMediaSource;
            this.spareMediaSource = temp;

            this.activePlayer.controls = true;
            this.sparePlayer.controls = false;
        } else {
            // convert array index to list index
            var listPos = this.trackOrder[arrayPos];

            var sources = this.getSources(listPos);
            this.activePlayer.innerHTML = sources;
            this.activePlayer.load();
        }

        // Update the record of the currently-playing track
        this.trackPos = arrayPos; // update based on array index position

        // Invalidate the pre-loaded track
        this.sparePlayerTrackPos = NaN;

        // Focus the active player so e.g. space does play/pause
        this.activePlayer.focus()
    }

    preloadNextTrack() {
        // if track isn't the last track in array of tracks, preload the next track
        if(this.trackPos < this.length - 1) {
            // convert array index to list index
            var listPos = this.trackOrder[this.trackPos + 1];

            var sources = this.getSources(listPos);
            this.sparePlayer.innerHTML = sources;
            this.sparePlayer.load();

            this.sparePlayerTrackPos = this.trackPos + 1;
        }
        else {
            // Don't preload at the end of the sequence (because it too complicated to bother)
            this.sparePlayerTrackPos = -1;
        }
    }

    prevTrack(){
        if(this.trackPos == 0)
            this.setTrack(0);
        else
            this.setTrack(this.trackPos - 1);
        this.activePlayer.play();
    }

    nextTrack(){
        // if track isn't the last track in array of tracks, go to next track
        if(this.trackPos < this.length - 1) {
            this.setTrack(this.trackPos+1);
            this.activePlayer.play();
        } else {
            // We have reached the end.
            // Reshuffle for next time
            if(this.shuffle)
                this.trackOrder = this.randomizeOrder(this.length);

            // Start back at the start, but do not play
            this.setTrack(0);

            // Reset the original title
            this.title.innerHTML = this.orignalTitleText;
            this.nowPlaying.innerHTML = "-"

            if(this.loop) {
                this.activePlayer.play();
            }
        }
    }

    setLoop(val){
        // Add/remove the loop highlight
        if(val)

        if(val === true)
            this.loop = true;
        else
            this.loop = false;
        return this.loop;
    }

    /** Called by clicking the shuffle button */
    toggleShuffle() {
        // Add/remove the shuffle highlight and update this.shuffle
        var shuffleButton = document.getElementById("shuffle");
        if(this.shuffle === true){
            shuffleButton.classList.add(this.selectedButtonClass);
            this.shuffle = false;
        } else {
            shuffleButton.classList.remove(this.selectedButtonClass);
            this.shuffle = true;
        }

        if(this.shuffle === true) {
            this.trackOrder = this.randomizeOrder(this.length);

            // Are we currently playing?
            var playing = ! this.activePlayer.paused;

            // Cue up the first (in shuffled order) track
            this.setTrack(0);

            // If we were previously playing, play immediately
            if(playing)
                this.activePlayer.play();
        } else {
            this.trackOrder = this.defaultOrder(this.length);

            // Just let the rest of the playlist play out in default order
            var currentSongLinks = this.playlist.getElementsByClassName(this.currentClass);
            if(currentSongLinks.length > 0) {
                var currentSongListItem = currentSongLinks[0].parentElement;
                var currentSongIndex = parseInt(currentSongListItem.getAttribute("index"));               
                this.trackPos = this.trackOrder.indexOf(currentSongIndex);
            }
            this.preloadNextTrack();
        }

        console.log("Shuffle order:" + this.trackOrder);
    }

    toggleLoop() {
        if(this.loop === true)
            this.loop = false;
        else
            this.loop = true;

        if(this.loop)
            this.loopButton.classList.add(this.selectedButtonClass);
        else
            this.loopButton.classList.remove(this.selectedButtonClass);
    }

    mimeType(extension) {
        if(extension=="mp3") return "mpeg";
        // All the others (m4a, ogg, wav, flac, wma) happen to be the same as the file extension
        return extension;
    }

    manageSizes() {
        // When we scroll down, or if the vertical height is very low, shrink the header
        if (this.content.scrollTop > 70 || this.content.clientHeight<300) {
            // Make everything 2/3 original size
            this.albumart.style.maxHeight = "10rem";
            this.header1.style.fontSize = "3.33rem";
            this.header2.style.fontSize = "2rem";
            this.header3.style.fontSize = "1.333rem";
        } else if (this.content.scrollTop < 5) {
            // Make everything its original size
            this.albumart.style.maxHeight = "12rem";
            this.header1.style.fontSize = "4rem";
            this.header2.style.fontSize = "2.4rem";
            this.header3.style.fontSize = "1.6rem";
        }
    }

    keypresses(event) {
        // Alpha-numeric characters and space form the actual search string
        if ( (event.key >= '0' && event.key <= '9')
          || (event.key >= 'a' && event.key <= 'z') 
          || (event.key == ' ' )) {
            this.searchbox.textContent += event.key;
            this.search_skip = 0;
        }
        // Backspace
        else if ( event.code == 'Backspace' ) {
            // Delete last character
            this.searchbox.textContent = this.searchbox.textContent.slice(0,-1);
        } else if ( event.code == 'Escape' ) {
            // Cancel the search
            this.cancelSearch();
            return;
        } 
        else if ( event.code == 'Tab' && event.shiftKey ) {
            this.search_skip -= 1;
        }
            else if ( event.code == 'Tab') {
            this.search_skip += 1;
        } else {
            return;
        }

        // Show the search box
        this.searchbox.classList.remove("hidden");

        // Clear any existing highlight
        var highlights = document.getElementsByClassName('search-highlight');
        for(var i = 0 ; i < highlights.length ; ++i) {
            highlights[i].classList.remove("search-highlight");
        }
        
        // Remove and clear the search box in a few seconds (unless we cancel)
        if(this.searchbox_timer_id != null) {
            clearTimeout(this.searchbox_timer_id);
            this.searchbox_timer_id = null;
        }
        this.searchbox_timer_id = setTimeout(this.cancelSearch, 4000, this);

        // Find all matching playlists and songs
        var needle = this.searchbox.textContent;
        console.log("Looking for " + needle);
        if(needle.length > 0) {
            var playlist_links = document.getElementsByClassName("playlistlink");
            var song_links = document.getElementsByClassName("songlink");
            var all_links = [];
            for (var i = 0 ; i < playlist_links.length ; ++i) {
                all_links.push(playlist_links[i]);
            }
            for (var i = 0 ; i < song_links.length ; ++i) {
                all_links.push(song_links[i]);
            }

            var matches = [];
            for (var i = 0 ; i < all_links.length ; ++i) {
                var link = all_links[i];
                var name = link.textContent.toLowerCase();

                if (name.includes(needle)) {
                    matches.push(link);
                }
            }

            if (matches.length > 0) {
                var index = this.search_skip % matches.length;
                while (index < 0) {
                    index += matches.length;
                }
                console.log("Skipping to index " + index);
                var link = matches[index];
                link.scrollIntoView({ behavior: "smooth", block: "center", inline: "center"});
                link.focus();
                link.classList.add("search-highlight");
                this.search_hightlighted = link;
            }
        }

        return;
    }
    
    cancelSearch() {
        console.log("Removing search");
        this.searchbox.classList.add("hidden");
        this.searchbox.textContent = "";
        this.search_skip = 0;
    }

    constructor(){
        // Set defaults and initialzing player 
        var classObj = this; // store scope for event listeners
        this.shuffle = false;
        this.currentClass = "current-song";
        this.selectedButtonClass = "selected";
        this.content = document.getElementsByClassName("content")[0]; /* the scrollable part including playlist and song links */
        this.playlist = document.getElementById("playlist").getElementsByTagName("ul")[0];
        this.length = this.playlist.getElementsByTagName("li").length;
        this.player1 = document.getElementById("audioPlayer1");
        this.player2 = document.getElementById("audioPlayer2");
        this.loop = false;
        this.trackPos = 0;
        this.trackOrder = this.defaultOrder(this.length);
        this.title = document.getElementById("title");
        this.orignalTitleText = title.innerHTML;
        this.albumart = document.getElementsByClassName("picture")[0];
        this.nowPlaying = document.getElementById("nowplaying");
        this.header1 = document.getElementsByTagName("h1")[0];
        this.header2 = document.getElementsByTagName("h2")[0];
        this.header3 = document.getElementsByTagName("h3")[0];
        this.shuffleButton = document.getElementById("shuffle");
        this.loopButton = document.getElementById("loop");
        this.searchbox = document.getElementById("searchbox");

        // At startup, player1 is the "active" one, player2 the spare
        this.activePlayer = this.player1;
        this.sparePlayer = this.player2;

        // No track is pre-loaded on the spare player
        this.sparePlayerTrackPos = NaN;

        // The searchbox timer id -- used to make the searchbox invisible after searching
        this.searchbox_timer_id = null;
        // The list item highlighted due to search
        this.search_hightlighted = null;
        // Skip to the n'th match
        this.search_skip = 0;

        // Hide the audio player footer and the play controls if there are no tracks
        if(this.length == 0) {
            document.getElementsByClassName("footer")[0].style.display = "none";
            document.getElementById("controls").style.display = "none";
        }

        // Get the equaliser canvas and set up the equaliser.
        // We will connect the player to it when we play a track.
        var canvas = document.getElementsByClassName("equalisercanvas")[0];
        this.context = new window.AudioContext();
        this.muneq = new Muneq(this.context, canvas);

        if(this.shuffle)
            this.trackOrder = this.randomizeOrder(this.length);

        // Cue up the first track (but don't play it)
        if(this.length > 0)
            this.setTrack(this.trackPos);

        var playlist_listitems = this.playlist.getElementsByTagName("li");
        for(var i=0 ; i<playlist_listitems.length ; ++i) {
            // Set an 'index' attribute for each track li
            var li = playlist_listitems[i];
            li.setAttribute("index", i);

            // Handle the track link click
            var link = playlist_listitems[i].getElementsByTagName("a")[0];
            link.addEventListener("click", function(e) {
                e.preventDefault();

                // set track based on index of the list item in the randomised order
                var listitem = getParentByTag(e.target, "li");
                var tracknum = parseInt(listitem.getAttribute("index"));
                var order = classObj.trackOrder.indexOf(tracknum);
                classObj.setTrack(order);
                classObj.activePlayer.play();
            });
        }

        // Handle end of track
        this.player1.addEventListener("ended", function(){
            classObj.nextTrack();
        });
        this.player2.addEventListener("ended", function(){
            classObj.nextTrack();
        });

        // Called when a track starts to play
        this.player1.addEventListener("play", function(){
            classObj.onPlay();
        });
        this.player2.addEventListener("play", function(){
            classObj.onPlay();
        });

        // When loading pauses on the active player (e.g. because enough if buffered), preload the next track
        this.player1.addEventListener("suspend", function() { 
            // If no track is currently preloaded, pre-load the next track
            if(isNaN(classObj.sparePlayerTrackPos) && classObj.player1.currentTime > 0) {
                classObj.preloadNextTrack();
            }
        });
        this.player2.addEventListener("suspend", function() { 
            // If no track is currently preloaded, pre-load the next track
            if(isNaN(classObj.sparePlayerTrackPos) && classObj.player2.currentTime > 0) {
                classObj.preloadNextTrack();
            }
        });

        // Sync volume changes and mute status between the two players
        this.player1.addEventListener("volumechange", function() {
            if(classObj.player2.volume != classObj.player1.volume) {
                classObj.player2.volume = classObj.player1.volume;
                localStorage.setItem("volume", classObj.player1.volume);
            }
            if(classObj.player2.muted != classObj.player1.muted) classObj.player2.muted = classObj.player1.muted;
        });
        this.player2.addEventListener("volumechange", function() {
            if(classObj.player1.volume != classObj.player2.volume) {
                classObj.player1.volume = classObj.player2.volume;
                localStorage.setItem("volume", classObj.player2.volume);                 
            } 
            if(classObj.player1.muted != classObj.player2.muted) classObj.player1.muted = classObj.player2.muted;
        });

        // If there is a stored volume, set volume to it; else to half.
        var volume = 0.5;
        if(localStorage.getItem("volume"))
            volume = localStorage.getItem("volume");
        this.activePlayer.volume = volume;

        // Register MediaSession controls (for e.g. Android integration)
        navigator.mediaSession.setActionHandler("nexttrack", function() {
            classObj.nextTrack();
        });
        navigator.mediaSession.setActionHandler("previoustrack", function() {
            classObj.prevTrack();
        });

        // Resize parts when scrolling or resizing, plus once upon loading (now)
        this.content.onscroll = function() {classObj.manageSizes();};
        window.onresize = function() {classObj.manageSizes();};
        this.manageSizes();

        // Register keypress listener to search/jump to items
        document.addEventListener("keydown", function(event) {
            return classObj.keypresses(event);
        });
    }

    init() {
        // Firefox does not allow us to createMediaElementSource() until the user has clicked on the page, so we
        // can't do this in the construcor.
        // Chrome does not allow createMediaElementSource() to be called more than once per player, so we can't
        // just create a new one each time we play.
        // Instead, create the MediaElementSources here the first time a play starts, which satisfies both restrictions.
        if(!this.initialised) {
            this.context.resume();
            this.activeMediaSource = this.context.createMediaElementSource(this.activePlayer);
            this.spareMediaSource = this.context.createMediaElementSource(this.sparePlayer);
            this.initialised = true;
        }

    }
}

function getParentByTag(elem, lookingFor) {
    lookingFor = lookingFor.toUpperCase();
    while (elem = elem.parentNode) if (elem.tagName === lookingFor) return elem;
  }
