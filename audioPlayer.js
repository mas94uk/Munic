/* Javascript audio player - based on github.com:NelsWebDev/BetterAudioPlaylist.git */

class AudioPlaylist{
    onPlay(){
        // Set the title and now-playing.
        // We do this here, rather than in setTrack(), so that it does not happen when the
        // page loads and nothing is yet playing.
        var listPos = this.trackOrder[this.trackPos]; // handle shuffle indices
        var link = $("#"+this.playlistId+ " li a").eq(listPos)[0];
        var nowPlaying = link.children[0].innerText.trim();
        if(link.childElementCount > 1 && link.children[1].innerText.length > 0) {
            nowPlaying = nowPlaying + " (" + link.children[1].innerText.trim() + ")";
        }
        this.title.innerHTML = nowPlaying;
        this.nowPlaying.innerHTML = nowPlaying;

        // Highlight the currently-playing track
        $("#"+this.playlistId+ " li").eq(listPos).addClass(this.currentClass);

        // Move the link to the middle of the screen
        link.scrollIntoView({ behavior: "smooth", block: "center", inline: "center"});
    }

    randomizeOrder(){
        for (var i = this.trackOrder.length - 1; i > 0; i--) {
            var j = Math.floor(Math.random() * (i + 1));
            var temp = this.trackOrder[i];
            this.trackOrder[i] = this.trackOrder[j];
            this.trackOrder[j] = temp;
        }
    }

    getSources(listPos) {
        var original_url = $("#"+this.playlistId+ " li a").eq(listPos).attr("href");

        // Generate a list of sources: the original, and transcoded alternatives
        // TODO: Only offer alternate formats if the back end offers transcoding.
        var source_template = '<source src="__FILE__" type="audio/__MIMETYPE__">';
        var parts = original_url.split("."); // get the stem and extension
        var sources = "";
        if(parts.length == 2) {
            var stem = parts[0];
            var original_format = parts[1];
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
        }

        return sources;
    }

    setTrack(arrayPos){
        // Remove the highlight
        $("."+this.currentClass).removeClass(this.currentClass);

        // If the spare player is already loaded with the requested track
        if(arrayPos == this.sparePlayerTrackPos) {
            // Stop the current player
            this.activePlayer.pause();
            this.activePlayer.innerHTML = "";

            // Make the spare player the active one and the active one the spare
            var temp = this.activePlayer;
            this.activePlayer = this.sparePlayer;
            this.sparePlayer = temp;

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
                this.randomizeOrder();

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
        if(val === true)
            this.loop = true;
        else
            this.loop = false;
        return this.loop;
    }

    setShuffle(val){
        if(val == this.shuffle) // if no change
            return val;
        else{
            if(val === true){
                this.randomizeOrder();
                this.shuffle = true;
            }
            else{
                this.shuffle = false;
                // empty track array, fill array with indexs in order
                this.trackOrder = [];
                for(var i = 0; i < this.length; i++){
                    this.trackOrder.push(i);
                }

                // jump array to track position of currently playing track
                this.trackPos = this.trackOrder.indexOf($("."+this.currentClass).index());
            }
            return this.shuffle;
        }
    }

    toggleShuffle(){
        if(this.shuffle === true)
            this.setShuffle(false);
        else
            this.setShuffle(true);

        this.setTrack(0);
        return this.shuffle;
    }

    toggleLoop(){
        if(this.loop === true)
            this.setLoop(false);
        else
            this.setLoop(true);
        return this.loop;
    }

    mimeType(extension){
        if(extension=="mp3") return "mpeg";
        // All the others (m4a, ogg, wav, flac, wma) happen to be the same as the file extension
        return extension;
    }

    manageSizes() {
        // When we scroll down, or if the vertical height is very low, shrink the header
        if (this.content.scrollTop > 20 || this.content.clientHeight<300) {
            // Make everything 2/3 original size
            this.albumart.style.maxHeight = "10rem";
            this.header1.style.fontSize = "3.33rem";
            this.header2.style.fontSize = "2rem";
            this.header3.style.fontSize = "1.333rem";
        } else {
            // Make everything its original size
            this.albumart.style.maxHeight = "15rem";
            this.header1.style.fontSize = "5rem";
            this.header2.style.fontSize = "3rem";
            this.header3.style.fontSize = "2rem";
        }
    }

    constructor(){
        // Set defaults and initialzing player 
        var classObj = this; // store scope for event listeners
        this.shuffle = false;
        this.playlistId = "playlist";
        this.currentClass = "current-song";
        this.content = document.getElementsByClassName("content")[0]; /* the scrollable part including playlist and song links */
        this.playlist = document.getElementById(this.playlistId);
        this.length = this.playlist.getElementsByTagName("li").length;
        this.player1 = document.getElementById("audioPlayer1");
        this.player2 = document.getElementById("audioPlayer2");
        this.loop = false;
        this.trackPos = 0;
        this.trackOrder = [];
        this.title = document.getElementById("title");
        this.orignalTitleText = title.innerHTML;
        this.albumart = document.getElementsByClassName("picture")[0];
        this.nowPlaying = document.getElementById("nowplaying");
        this.header1 = document.getElementsByTagName("h1")[0];
        this.header2 = document.getElementsByTagName("h2")[0];
        this.header3 = document.getElementsByTagName("h3")[0];
        for(var i = 0; i < this.length; i++){
            this.trackOrder.push(i);
        }

        // At startup, player1 is the "active" one, player2 the spare
        this.activePlayer = this.player1;
        this.sparePlayer = this.player2;

        // No track is pre-loaded on the spare player
        this.sparePlayerTrackPos = NaN;

        // Start the volume at half
        this.activePlayer.volume = 0.5;

        // Hide the audio player footer if there are no tracks
        if(this.length == 0) {
            document.getElementsByClassName("footer")[0].style.display = "none";
        }

        if(this.shuffle)
            this.randomizeOrder();

        if(this.length > 0) {
            this.setTrack(this.trackPos);
        }

        // Handle track link clicks
        $("#"+this.playlistId+" li a ").click(function(e){
            e.preventDefault();

            // set track based on index of the list item in the ranomised order
            classObj.setTrack(classObj.trackOrder.indexOf($(this).parent().index()));
            classObj.activePlayer.play();
        });

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
            if(classObj.player2.volume != classObj.player1.volume) classObj.player2.volume = classObj.player1.volume;
            if(classObj.player2.muted != classObj.player1.muted) classObj.player2.muted = classObj.player1.muted;
        });
        this.player2.addEventListener("volumechange", function() {
            if(classObj.player1.volume != classObj.player2.volume) classObj.player1.volume = classObj.player2.volume;
            if(classObj.player1.muted != classObj.player2.muted) classObj.player1.muted = classObj.player2.muted;
        });

        // Resize parts when scrolling or resizing, plus once upon loading (now)
        this.content.onscroll = function() {classObj.manageSizes();};
        window.onresize = function() {classObj.manageSizes();}
        this.manageSizes();
    }
}
