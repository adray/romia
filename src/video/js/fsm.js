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
            var candidates = []

            if (data.next !== undefined) {
                data.state = data.next;
                data.next = undefined;
                var paths = data.machine[data.state].paths;
                for (var i = 0; i < paths.length; i++) {
                    var candidate = { path: i, state: data.state };
                    candidates.push(candidate);
                }
            } else {
                const transitions = state.paths[data.path].transitions;
                if (transitions !== null && transitions !== undefined && transitions.length > 0) {
                    for (var i = 0; i < transitions.length; i++) {
                        const state = transitions[i];
                        var paths = data.machine[state].paths;
                        for (var j = 0; j < paths.length; j++) {
                            var candidate = { path: j, state: state };
                            candidates.push(candidate);
                        }
                    }
                }
            }
            
            if (candidates.length > 0) {
                var chosen = candidates[Math.floor(Math.random() * candidates.length)];
                data.state = chosen.state;
                data.path = chosen.path;
            }

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

