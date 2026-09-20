//
// Message data
//

"use strict";

function createShow(callback) {

    var data = {
        callback: callback,
        shows: undefined,
        show: undefined,
        index: 0,
        init: function() {
            fetch("/api/show-list/")
                .then((r) => {
                    return r.json();
                })
                .then((j) => {
                    data.shows = j;
                    data.getShow(data.shows.default);
                });
        },
        getShow: function(id) {
            fetch("/api/show/" + id)
                .then((r) => {
                    return r.json();
                })
                .then((j) =>
                {
                    data.show = j;
                    if (data.callback !== undefined) {
                        data.callback();
                    }
                });
        }
    };

    data.init();

    return {
        data: data,
        getNext: function() {
            const next = data.show[data.index];
            data.index += 1;
            return next;
        }
    };
}

