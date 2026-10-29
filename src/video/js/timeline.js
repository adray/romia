//
// Timeline management for video playback
//

"use strict";


function createTimeline() {
    var timeline = {
        audio: [],
        videos: [],
        subtitles: [],
        time: 0,
        audioPointer: 0,
        videoPointer: 0,
        subtitlePointer: 0,
        addAudio: function(event, time) {
            timeline.audio.push({event: event, time: time});
        },
        addSubtitle: function(subtitle, time) {
            timeline.subtitles.push({subtitle: subtitle, time: time});
        },
        addVideo: function(video, clipLength) {
            var time = timeline.time;
            if (timeline.videos.length > 0) {
                const lastClip = timeline.videos[timeline.videos.length - 1];
                time = lastClip.time + lastClip.clipLength;
                if (time < timeline.time) {
                    console.warn("Timeline time is ahead of the calculated video time.");
                }
            }
            timeline.videos.push({video: video, time: time, buffered: false, clipLength: clipLength });
            return time;
        },
        getTime: function() {
            return timeline.time;
        },
        getEndTime: function() {
            if (timeline.videos.length > 0) {
                var lastClip = timeline.videos[timeline.videos.length - 1];
                return lastClip.time + lastClip.clipLength;
            }
            return timeline.time;
        },
        update: function(time) {
            timeline.time = time;
            // Remove any videos that have ended
            while (timeline.videos.length > 0 && timeline.videos[0].time + timeline.videos[0].clipLength <= timeline.time) {
                timeline.videos.shift();
                if (timeline.videoPointer > 0) {
                    timeline.videoPointer--;
                }
            }
            // Remove any audio events that have passed
            while (timeline.audio.length > 0 && timeline.audio[0].time + 10000 <= timeline.time) {
                timeline.audio.shift();
                if (timeline.audioPointer > 0) {
                    timeline.audioPointer--;
                }
            }
        },
        getNextVideo: function() {
            if (timeline.videoPointer < timeline.videos.length) {
                var clip = timeline.videos[timeline.videoPointer++];
                clip.buffered = true;
                return { video: clip.video, time: clip.time, clipLength: clip.clipLength };
            }
            return null;
        },
        getNextAudio: function() {
            if (timeline.audioPointer < timeline.audio.length) {
                var audio = timeline.audio[timeline.audioPointer];
                if (timeline.time >= audio.time) {
                    timeline.audioPointer++;
                    return audio.event;
                }
            }
            return null;
        },
        getNextSubtitle: function() {
            if (timeline.subtitlePointer < timeline.subtitles.length) {
                var subtitle = timeline.subtitles[timeline.subtitlePointer];
                if (timeline.time >= subtitle.time) {
                    timeline.subtitlePointer++;
                    return subtitle.subtitle;
                }
            }
            return null;
        },
        render: function() {
            // This function can be used to render the timeline visually
            var html = "<div class='timeline'>"; 
            html += "<div>Current Time: " + timeline.time + "ms</div>";
            for (var i = this.videoPointer - 1; i >= 0; i--) {
                var clip = timeline.videos[i];
                if (clip.time >= timeline.time) {
                    html += "<div>Video: " + clip.video + " at " + clip.time + "ms</div>";
                } else {
                    break;
                }
            }

            for (var i = this.videoPointer; i < timeline.videos.length; i++) {
                var clip = timeline.videos[i];
                if (clip.time >= timeline.time) {
                    html += "<div>Video: " + clip.video + " at " + clip.time + "ms</div>";
                }
            }

            for (var i = 0; i < timeline.audio.length; i++) {
                var audio = timeline.audio[i];
                if (audio.time >= timeline.time) {
                    html += "<div>Audio: " + audio.event + " at " + audio.time + "ms</div>";
                }
            }
            for (var i = 0; i < timeline.subtitles.length; i++) {
                var subtitle = timeline.subtitles[i];
                if (subtitle.time >= timeline.time) {
                    html += "<div>Subtitle: " + subtitle.subtitle + " at " + subtitle.time + "ms</div>";
                }
            }
            html += "</div>";
            return html;
        }
    };
    return timeline;
}
