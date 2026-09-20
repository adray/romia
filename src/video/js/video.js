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

/*const show = createShow(() => {
    pushMessage(show.getNext());
});*/
const engine = createPlaybackEngine();
const fsm = createFSM((initialized) => {
    populateState(fsm);
    if (initialized) {
        populateFsms(fsm);
        engine.start(() => {
            // Enqueue new clip(s)
            engine.enqueue(fsm.next());
        });   
    }
});

