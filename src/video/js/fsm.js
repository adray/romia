//
// Finite state machine
//

"use strict";

function createFSM(callback) {
    var data = {
        state: 0,
        path: 0,
        clip: 0,
        loop: 0,
        next: undefined,
        interrupt: false,
        machine: undefined,
        fsms: undefined,
        initialized: false,
        callback: callback,
        init: function() {
            fetch("/api/fsm-list/").then((res) => {
                return res.json();
            })
            .then((res) => {
                const defaultFsm = res.default;
                data.fsms = res.items;
                data.loadFsm(defaultFsm);
            });
        },
        loadFsm: function(id) {
            fetch("/api/fsm/" + id).then((res) => {
                    return res.json();
                })
                .then((res) => {
                    data.machine = res;
                    if (data.callback !== undefined) {
                        data.callback(!data.initialized);
                        data.initialized = true;
                    } 
                });
        },
        chooseNextState: function(state) {
            if (data.next !== undefined) {
                data.state = data.next;
                data.next = undefined;
            } else {
                const transitions = state.paths[data.path].transitions;
                if (transitions !== null && transitions !== undefined && transitions.length > 0) {
                    const randomIndex = Math.floor(Math.random() * transitions.length);
                    data.state = transitions[randomIndex];
                }
            }
            const paths = data.machine[data.state].paths;
            data.path = Math.floor(Math.random() * paths.length);
            data.clip = 0;
            data.loop = 0;
        }
    };

    data.init();

    return {
        data: data,
        next: function() {
            const state = data.machine[data.state];
            const path = state.paths[data.path];
            const next = path.clips[data.clip];

            data.clip++;
            if (data.clip === path.clips.length || data.interrupt) {
                var changeState = true;
                if (state.loop && !data.interrupt) {
                    data.loop++;
                    changeState = data.loop >= state.loop_count;
                    if (!changeState) {
                        data.clip = 0;
                    }
                }
                data.interrupt = false;

                if (changeState) {
                    // Pick a random transition
                    data.chooseNextState(state);
                }
            }

            return next;
        },
        getStates: function() {
            return data.machine;
        },
        changeState: function(state) {
            data.next = state;
            data.interrupt = true;
        },
        getFsm: function() {
            return data.fsms;
        },
        changeFsm: function(id) {
            data.loadFsm(id);

            data.state = 0;
            data.path = 0;
            data.clip = 0;
            data.loop = 0;
        }
    };
}

