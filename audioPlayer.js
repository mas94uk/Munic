/* Javascript audio player - based on github.com:NelsWebDev/BetterAudioPlaylist.git */

/*
    Default constructor configuration:
        autoplay: false,
        shuffle: false,
        loop: false,
        playerId: "audioPlayer",
        playlistId: "playlist",
        currentClass: "current-song"
        
    Methods:
        setLoop
        setShuffle
        toggleShuffle
        toggleLoop
        prevTrack
        nextTrack
    
    Can access player by .player variable
    example playlist.player.pause();
*/
 
class AudioPlaylist{
    randomizeOrder(){
        for (var i = this.trackOrder.length - 1; i > 0; i--) {
            var j = Math.floor(Math.random() * (i + 1));
            var temp = this.trackOrder[i];
            this.trackOrder[i] = this.trackOrder[j];
            this.trackOrder[j] = temp;
        }
        return this.trackOrder;
    }
    setTrack(arrayPos){
        var liPos = this.trackOrder[arrayPos]; // convert array index to html index
        var original_url = $("#"+this.playlistId+ " li a").eq(liPos).attr("href");

        // Generate a list of sources: the original, and transcoded alternatives
        // TODO: Only offer alternate formats if the back end offers transcoding.
        var source_template = '<source src="__FILE__" type="audio/__MIMETYPE__">'
        var parts = original_url.split(".") // get the stem and extension
        var sources = ""
        if(parts.length == 2) {
            var stem = parts[0]
            var original_format = parts[1]
            // Put the original format first, except if it is FLAC (because the bandwidth use is too high)
            if(original_format != "flac") {
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
            // Put FLAC last, but only if that is the original format -- never offer to transcode to flac
            if(original_format == "flac") {
                sources = sources + source_template.replace("__FILE__", original_url).replace("__MIMETYPE__", "flac");
            }
        }
        this.player.innerHTML = sources;
        this.player.load();

        $("."+this.currentClass).removeClass(this.currentClass);
        $("#"+this.playlistId+ " li").eq(liPos).addClass(this.currentClass);
        this.trackPos = arrayPos; // update based on array index position
    }
    prevTrack(){
        if(this.trackPos == 0)
            this.setTrack(0);
        else
            this.setTrack(this.trackPos - 1);
        this.player.play();
    }
    nextTrack(){
        // if track isn't the last track in array of tracks, go to next track
        if(this.trackPos < this.length - 1) {
            this.setTrack(this.trackPos+1);
            this.player.play();
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

            if(this.loop)
            {
                this.player.play();
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
                this.trackPos =  this.trackOrder.indexOf($("."+this.currentClass).index());
            }
            return this.shuffle;
        }
    }
    toggleShuffle(){
        if(this.shuffle === true)
            this.setShuffle(false);
        else
            this.setShuffle(true);
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
    constructor(config = {} ){
        // Set defaults and initialzing player 
        var classObj = this; // store scope for event listeners
        this.shuffle = (config.shuffle === true) ? true : false;
        this.playerId = (config.playerId) ? config.playerId : "audioPlayer";
        this.playlistId = (config.playlistId) ? config.playlistId : "playlist";
        this.currentClass = (config.currentClass) ? config.currentClass : "current-song"
        this.length = $("#"+this.playlistId+" li").length; 
        this.player = $("#"+this.playerId)[0];
        this.autoplay = (config.autoplay === true || this.player.autoplay) ? true : false;
        this.loop = (config.loop === true) ? true : false;
        this.trackPos = 0;
        this.trackOrder = [];
        this.title = $("#title")[0];
        this.orignalTitleText = title.innerHTML;
        this.nowPlaying = document.getElementById("nowplaying");
        for(var i = 0; i < this.length; i++){
            this.trackOrder.push(i);
        }

        // Hide the audio player (and the gap left for it) if there are no tracks
        if(this.length == 0) {
            document.getElementById("playerdiv").style.display = "none";
            document.getElementById("playergap").style.display = "none";
        }
        
        if(this.shuffle)
            this.randomizeOrder();
        
        this.setTrack(this.trackPos);
        if(this.autoplay)
            this.player.play();
        
        // Handle track link clicks
        $("#"+this.playlistId+" li a ").click(function(e){
            e.preventDefault();
            // set track based on index of 
            classObj.setTrack(classObj.trackOrder.indexOf($(this).parent().index()));
            classObj.player.play();
        });
        
        // Handle end of track
        this.player.addEventListener("ended", function(){
            classObj.nextTrack();
        });

        // Called when a track starts to play
        this.player.addEventListener("play", function(){
            // Set the title and now-playing.
            // We do this here, rather than in setTrack(), so that it does not happen when the
            // page loads and nothing is yet playing. 
            var liPos = classObj.trackOrder[classObj.trackPos]; // convert array index to html index
            var nowPlaying = $("#"+classObj.playlistId+ " li a").eq(liPos)[0].text;
            classObj.title.innerHTML = nowPlaying;
            classObj.nowPlaying.innerHTML = nowPlaying;
        });

    }
}

