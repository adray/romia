//
// Playback engine
//

"use strict";

function createPlaybackEngine() {
    var data = {
        mediaQueue: [],
        audioQueue: [],
        mediaSource: new MediaSource(),
        audioElement: new Audio(),
        audioPlaying: false,
        sourceBuffer: undefined,
        callback: undefined,
        wakeLock: undefined,
        requestMore: async function () {
            if (data.callback !== undefined &&
                data.mediaQueue.length == 0) {
                data.callback();
            }
        },
        onSourceOpen: async function() {
            data.sourceBuffer = data.mediaSource.addSourceBuffer('video/mp4; codecs="avc1.64001E"');
            data.sourceBuffer.mode = "sequence";

            data.sourceBuffer.addEventListener("error", () => {
                console.log("Error occurred during decoding");
            });
            data.sourceBuffer.addEventListener("abort", () => {
                console.log("Abort");
            });

            data.sourceBuffer.addEventListener("updateend", () => {
                data.checkBufferHealth();
            });
            
            if (data.mediaQueue.length > 0) {
                data.appendClip(data.mediaQueue.shift().video);
            }
        },
        appendClip: async function(clipName) {
            const buffer = await fetch(clipName).then((res) =>
                res.arrayBuffer(),
            );

            data.sourceBuffer.appendBuffer(buffer);
        },
        checkBufferHealth: function() {
            if (!data.sourceBuffer || data.sourceBuffer.buffered.length === 0) return;

            const bufferedEnd = data.sourceBuffer.buffered.end(data.sourceBuffer.buffered.length - 1);
            const bufferedAhead = bufferedEnd - video.currentTime;

            const TARGET_BUFFER_SECONDS = 10; // ~2-3 clips at ~5s each

            if (bufferedAhead < TARGET_BUFFER_SECONDS && data.mediaQueue.length === 0 && data.callback) {
                data.callback(); // ask caller to enqueue more
            }

            if (data.mediaQueue.length > 0 && !data.sourceBuffer.updating) {
                data.appendClip(data.mediaQueue.shift().video);
            }
        },
    };

    return {
        data: data,
        start: function(callback) {
            // Set the video MediaSource
            const url = URL.createObjectURL(data.mediaSource);
            const video = document.querySelector("video");
            video.src = url;
            video.addEventListener("timeupdate", () => data.checkBufferHealth());

            data.callback = callback;
            data.mediaSource.addEventListener("sourceopen", data.onSourceOpen);
            data.requestMore();

            video.addEventListener("play", () => {
                data.audioElement.play().catch((error) => {
                    console.error("Error playing audio:", error);
                });

                if ("wakeLock" in navigator) {
                    navigator.wakeLock.request("screen").then((wakeLock) => {
                        data.wakeLock = wakeLock;
                    }).catch((error) => {
                        console.error("Error acquiring wake lock:", error);
                    });
                }
            });
            video.addEventListener("pause", () => {
                data.audioElement.pause();
                if (data.wakeLock) {
                    data.wakeLock.release().then(() => {
                        data.wakeLock = undefined;
                    }).catch((error) => {
                        console.error("Error releasing wake lock:", error);
                    });
                }
            });
            data.audioElement.addEventListener('ended', () => {
                data.audioPlaying = false;
                data.audioElement.src = "";
                if (data.audioQueue.length > 0) {
                    const nextAudio = data.audioQueue.shift();
                    data.audioElement.src = nextAudio;
                    data.audioElement.play();
                    data.audioPlaying = true;
                }
            });
        },
        enqueue: function(video) {
            data.mediaQueue.push(video);
        },
        enqueueAudio: function(audioURL) {
            data.audioQueue.push(audioURL);

            if (data.audioQueue.length === 1 && !data.audioPlaying) {
                data.audioQueue.shift();
                data.audioElement.src = audioURL;
                data.audioElement.play().catch((error) => {
                    console.error("Error playing audio:", error);
                });
                data.audioPlaying = true;
            }
        },
    };
}
