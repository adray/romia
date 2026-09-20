#include "roServer.h"
#include "roVideo.h"

int main( const int numArgs, const char** args) {

    roServer server;
    //server.load_fsm();
    server.load_custom_fsm();
    //server.load_graph();
    server.add_route_get("/", "scripts/index.txt");
    server.add_route_get("/api/fsm/:id", "scripts/fsm.txt");
    server.add_route_get("/api/fsm-list/", "scripts/fsm-list.txt");
    server.add_route_get("/api/show-list/", "scripts/show-list.txt");
    server.add_route_get("/api/show/:id", "scripts/show.txt");
    //server.add_directory("/css", "bootstrap-4.3.1-dist/css");
    //server.add_directory("/js", "bootstrap-4.3.1-dist/js");
    server.add_directory("/jquery", "jquery");
    server.add_directory("/js", "js");
    server.add_directory("/video", "/home/adam/.AI/Desktop/Romia/Video-Wan-2.2/Frags");
    server.start(7777);

    return 0;
}
