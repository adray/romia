//
// Video model
//

"use strict";

function populateState(fsm) {
    var states = fsm.getStates();
    var optionElements = [];

    $.each(states, function(key, value) {
        optionElements.push('<option value="' + key + '">' + value.state + '</option>');
    });

    $('#select-state').html(optionElements.join(''));
    $('#select-state').on('change', function (e) {
        //var optionSelected = $("option:selected", this);
        var valueSelected = this.value;
        fsm.changeState(valueSelected);
    });
}

function populateFsms(fsm) {
    var items = fsm.getFsm();
    var optionElements = [];

    $.each(items, function(_, value) {
        if (value.num_states > 0) {
            optionElements.push('<option value="' + value.id + '">' + value.name + '</option>');
        }
    });

    $('#select-fsms').html(optionElements.join(''));
    $('#select-fsms').on('change', function (e) {
        //var optionSelected = $("option:selected", this);
        var valueSelected = this.value;
        fsm.changeFsm(valueSelected);
        populateState(fsm);
    });
}

function pushMessage(msg) {
    $('#div-message').html(msg);
}

//
// Coordinator for managing interactions between the playback engine, timeline, and FSM
//

function createCoordinator(fsm) {
    const clipLengthMilliseconds = 5062.5; // 81 frames at 16fps
    const timeline = createTimeline();
    const engine = createPlaybackEngine();
    const voice = createEventListener((data) => {
        for (var i = 0; i < data.events.length; i++) {
            const event = data.events[i];
            if (event.type === "update" || event.type === "audio") {
                fsm.update(event.state, event.interrupt);
                // Fill in clips until the FSM reaches the next state
                const nextState = fsm.getNextState();
                var time = timeline.getEndTime();
                while (fsm.getCurrentState() !== nextState) {
                    const clip = fsm.next();
                    time = timeline.addVideo(clip, clipLengthMilliseconds) + clipLengthMilliseconds;
                }
                // Now, add the audio if present
                if (event.type === "audio") {
                    timeline.addAudio(event.data, time);
                }
            }
        }
    });

    const coordinator = {
        timeline: timeline,
        engine: engine,
        voice: voice,
        fetchNextClip: function() {
            var clip = timeline.getNextVideo();
            if (!clip) {
                // If no clip is available, request the FSM to provide the next clip
                timeline.addVideo(fsm.next(), clipLengthMilliseconds);
                clip = timeline.getNextVideo();
            }

            engine.enqueue(clip);
        },
        playNextAudio: function() {
            var audio = timeline.getNextAudio();
            if (audio) {
                engine.enqueueAudio(audio);
            }
        }
    };

    const timeUpdate = function() {
        timeline.update(video.currentTime * 1000);
        coordinator.playNextAudio();
        $('#div-timeline').html(timeline.render());
    };

    // Get the video element from the DOM, read the video time periodically to update the timeline
    const video = document.querySelector("video");
    setInterval(timeUpdate, 100); // Update every 100 milliseconds

    return coordinator;
};


const fsm = createFSM((initialized) => {
    populateState(fsm);
    if (initialized) {
        populateFsms(fsm);
        const coordinator = createCoordinator(fsm);
        coordinator.engine.start(() => {
            // Enqueue new clip(s)
            coordinator.fetchNextClip();
        });   
    }
});

