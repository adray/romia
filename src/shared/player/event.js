//
// This script handles published events for the video application.
//

"use strict";

function createEventListener(callback) {
    var data = {
        id: 0,
        init: function() {
            fetch('/api/event/latest')
                .then(response => response.json())
                .then(responseData => {
                    data.id = responseData.next_id;
                    data.timer = setInterval(data.poll, 1000);
                });
        },
        poll: function() {
            fetch('/api/event/next/' + data.id)
                .then(response => response.json())
                .then(responseData => {
                    var status = responseData.status;
                    if (status !== "ok") {
                        return;
                    }
                    if (callback) {
                        callback(responseData);
                    }
                    data.id = responseData.next_id;
                });
        },
        timer: null
    };
    data.init();

    return data;
}
