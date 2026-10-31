//
// Finite state machine
//

"use strict";

function createFSM(onInitialCreate, onFsmChanged, onModelChanged) {
    var data = {
        model: 0,
        state: 0,
        path: 0,
        clip: 0,
        loop: 0,
        next: undefined,
        interrupt: false,
        models: undefined,
        machine: undefined,
        fsms: undefined,
        initialized: false,
        modelChanged: false,
        onInitialCreate: onInitialCreate,
        onFsmChanged: onFsmChanged,
        onModelChanged: onModelChanged,
        init: function() {
            fetch("/api/model-list").then((res) => {
                return res.json();
            })
            .then((res) => {
                data.models = res.models;
                if (data.models.length > 0) {
                    data.model = 0;
                    data.modelChanged = true;
                    data.listFsm(data.model);
                }
            });
        },
        listFsm: function(id) {
            fetch("/api/fsm-list/" + id).then((res) => {
                return res.json();
            })
            .then((res) => {
                const defaultFsm = res.default;
                data.fsms = res.items;
                data.loadFsm(defaultFsm);
            });
        },
        loadFsm: function(id) {
            fetch("/api/fsm/" + data.model + "/" + id).then((res) => {
                    return res.json();
                })
                .then((res) => {
                    data.machine = res;
                    data.fsmChanged();
                    if (data.modelChanged && data.onModelChanged !== undefined) {
                        data.onModelChanged();
                        data.modelChanged = false;
                    }
                    if (data.onInitialCreate !== undefined && data.initialized === false) {
                        data.onInitialCreate();
                        data.initialized = true;
                    } 
                });
        },
        fsmChanged: function() {
            data.state = 0;
            data.path = 0;
            data.clip = 0;
            data.loop = 0;
            data.next = undefined;
            data.interrupt = false;     
            if (data.onFsmChanged !== undefined) {
                data.onFsmChanged();
            }
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
        getCurrentState: function() {
            return data.state;
        },
        getNextState: function() {
            return data.next;
        },
        changeFsm: function(id) {
            data.loadFsm(id);
        },
        changeModel: function(id) {
            data.model = id;
            data.modelChanged = true;
            data.listFsm(id);
        },
        update: function(state, interrupt) {
            // look up the state name in the fsm to find the id
            var fsm = data.machine;
            var stateId = null;
            for (var i = 0; i < fsm.length; i++) {
                if (fsm[i].state === state) {
                    stateId = i;
                    break;
                }
            }

            var ok = false;
            if (stateId !== null) {
                data.next = stateId;
                data.interrupt = interrupt;
                ok = true;
            }
            return ok;
        }
    };
}

