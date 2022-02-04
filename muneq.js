/* Javascript audio equaliser and visualiser for Munic */

class Muneq {
	// TODO Visualise the data on the canvas

	// TODO changes should happen on mouseup, or mousemove if previously got a mousedown.
	mousemove(event) {
		// Get the position of the click within the canvas.
		// Note that y=0 is at the top.
		// Assume the canvas does not have borders. (User should make sure it doesn't!)
	    const rect = this.canvas.getBoundingClientRect();
	    const x = event.clientX - rect.left;
	    const y = event.clientY - rect.top;

	    // Work out which band this is in.
	    var bandWidth = rect.width / this.numBands;
	    var band = Math.floor(x / bandWidth);

	    if(this.mousedown) {
		    // Work out the fraction "up" - 1 being at the top, -1 at the bottom.
		    var up = 1 - 2*(y/rect.height) 

		    // Work out the gain corresponding to this position
		    var gain = up * this.maxGain;

		    // Set the gain of this band
		    this.filters[band].gain.value = gain;

		    // Store the value
		    localStorage.setItem(band, gain);
		}

	    // Update the frequency response curve and highlight the band we are hovering over
	    this.draw(band);
    }

    /* Draw a frequency response curve on the canvass */
    draw(band) {
    	var context = this.canvas.getContext("2d");
    	var width = this.canvas.width;
    	var height = this.canvas.height;
    	context.clearRect(0, 0, width, height);
    	context.fill();	

    	if(band >= 0) {
	    	var bandWidth = width / this.numBands;
			context.beginPath();
			context.rect(band*bandWidth, 0, bandWidth, height);
			context.fillStyle = "rgba(0,0,0,0.2)";
			context.fill();
		}

    	// Get a list of frequencies.
    	// We want as many frequency response points as the canvas has pixels horizontally
    	var freqs = this.getFreqencies(width);

    	// Create an array to hold the magnitude response
    	var response = new Float32Array(width);
    	response.fill(1);

    	// An array to hold each magnitude and phase response.
	    var mag = new Float32Array(width);
    	var pha = new Float32Array(width);

    	// Get the frequency response of each filter in turn, and multiply them to get overall
    	for(var i=0 ; i<this.numBands ; ++i) {
	    	// Get the frequency response
    		this.filters[i].getFrequencyResponse(freqs, mag, pha);

    		// Multiply this into the overall response
    		for(var j=0 ; j<width ; ++j) {
    			response[j] *= mag[j];
    		}
    	}

    	// We now have the response of the whole system, as a multiplier.
    	// Take the logs of it, so that a gain (>1) becomes a positive number, and attenuation negative.
    	for(var i=0 ; i<width ; ++i) {
    		response[i] = Math.log(response[i]);
    	}

    	// Get the max and min response
    	var max = -Infinity
    	var min = Infinity
    	for(var i=0 ; i<width; ++i) {
    		if (response[i] > max) max = response[i];
    		if (response[i] < min) min = response[i];
    	}

    	// We will make a response range of +-2 (determined by experimentation) fill the canvas height
    	var factor = height / 4;
    	var offset = height / 2;

    	// Draw the response on the canvas
    	context.beginPath();
		context.fillStyle = "rgba(0,0,0,0)";
		context.strokeStyle = "rgba(220,220,220,0.4)"
    	context.moveTo(0, offset - response[0]*factor);
    	for(var i=1; i<width ; ++i) {
    		context.lineTo(i, offset - response[i]*factor);
    	}
    	context.stroke();
    }

    getFreqencies(num) {
		var log_fmin = Math.log(this.fmin);
		var log_fmax = Math.log(this.fmax);
		var gap = (log_fmax - log_fmin) / (num-1)

		var freqs = new Float32Array(num);
		for(var i=0 ; i<num ; ++i) {
			 freqs[i] = Math.E**(log_fmin + gap*i)
		}
		return freqs;
    }

	constructor(audioContext, canvas) {
		this.audioContext = audioContext;
		var classObj = this;
		this.mousedown = false;
		this.canvas = canvas;

		// Number of equaliser bands to provide
		this.numBands = 10;

		// Max gain or attenuation (dB)
		this.maxGain = 12

		// Useful frequency range: 20-20kHz
		this.fmin = 20;
		this.fmax = 20000;

		// Create an array of BiQuadFilter.
		// Set their centre frequencies in the middle of each of numBands bands.
		// Set their gain to the stored value.
		this.filters = new Array(this.numBands);
		var log_fmin = Math.log(this.fmin);
		var log_fmax = Math.log(this.fmax);
		var numFreqs = (this.numBands * 2) + 1;
		var gap = (log_fmax - log_fmin) / (numFreqs-1)

		var freqs = this.getFreqencies(numFreqs);
		for(var i=0 ; i<this.numBands ; ++i) {
			 var filter = audioContext.createBiquadFilter();
			 filter.type = "peaking";
			 var freq = Math.round(freqs[2*i + 1])	;
			 filter.frequency.value = freq;
			 filter.Q.value = 1.75;	// Determined heuristically

 		    // Set the gain of this band to the stored value, if one exists.
 		    if(localStorage.getItem(i)) {
		    	filter.gain.value = localStorage.getItem(i);
 		    }

			this.filters[i] = filter;

			// Chain the filters together
			if(i>0) {
				this.filters[i-1].connect(this.filters[i]);
			}
		}

		// Connect the final node to the destination (the speakers)
		this.filters[this.numBands-1].connect(audioContext.destination)

		// Listen for clicks and mouse movements on the canvas
		canvas.addEventListener("mousedown", function(e) {
			classObj.mousedown = true;
			classObj.mousemove(e);
		});
		canvas.addEventListener("mouseup", function(e) {
			classObj.mousedown = false;
		});
		canvas.addEventListener("mouseout", function(e) {
			classObj.mousedown = false;
			classObj.draw(-1);
		});
		canvas.addEventListener("mousemove", function(e) {
			classObj.mousemove(e);
		});


	    // Draw the frequency response curve
	    this.draw(-1);
	}


	/* Set the input to the filter chain.
	   Note that this is back-to-front from the way it's supposed to work -- we SHOULD do 'source.connect(dest)'.
	   We might sort this out in future by implementing the eq as its own AudioNode. */
	setInput(sourceNode) {
		sourceNode.connect(this.filters[0]);
	}
}