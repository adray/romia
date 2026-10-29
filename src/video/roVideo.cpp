#include "roServer.h"
#include "roVideo.h"

int main( const int numArgs, const char** args) {

    roServer server;
    server.load_models();
    server.add_route_get("/", "scripts/index.txt");
    server.add_route_get("/gan.html", "scripts/gan.txt");
    server.add_route_get("/api/fsm/:model/:id", "scripts/fsm.txt");
    server.add_route_get("/api/fsm-list/:model", "scripts/fsm-list.txt");
    server.add_route_get("/api/model-list", "scripts/model-list.txt");
    server.add_route_get("/api/event/next/:id", "scripts/event.txt");
    server.add_route_get("/api/event/latest", "scripts/event-latest.txt");
    server.add_route_post("/api/event", "scripts/event-post.txt");
    server.add_route_post("/api/speak", "scripts/audio-post.txt");
    //server.add_directory("/css", "bootstrap-4.3.1-dist/css");
    //server.add_directory("/js", "bootstrap-4.3.1-dist/js");
    server.add_directory("/jquery", "jquery");
    server.add_directory("/js", "js");
    server.add_directory("/css", "css");
    server.add_directory("/audio", "audio");
    server.start(7777);

    return 0;
}
