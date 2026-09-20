#include "roStudio.h"
#include "roServer.h"

int main( const int numArgs, const char** args) {

    roServer server;
    server.load_fsm_approvals("./models/romia/fsm_approvals.json");
    server.load_approvals("./models/romia/approvals.json");
    server.add_route_get("/", "scripts/index.txt");
    server.add_route_get("/search", "scripts/search.txt");
    server.add_route_get("/approvals/:id", "scripts/approvals.txt");
    server.add_route_get("/approvals-groups", "scripts/approve-groups.txt");
    server.add_route_get("/styles.css", "scripts/styles.txt");
    server.add_route_get("/approvals.js", "scripts/approvals.js.txt");
    server.add_route_get("/groups.js", "scripts/approvals-group.js.txt");
    server.add_route_get("/search.js", "scripts/search.js.txt");
    server.add_route_get("/api/video/:id", "scripts/api-video-json.txt");
    server.add_route_get("/api/search/:term", "scripts/api-search.txt");
    server.add_route_get("/api/group", "scripts/api-group.txt");
    server.add_route_get("/api/group/approve", "scripts/api-group-approve.txt");
    server.add_route_get("/api/group/reject", "scripts/api-group-reject.txt");
    server.add_route_post("/api/approve/:video/:frame", "scripts/api-approve.txt");
    server.add_directory("/css", "bootstrap-4.3.1-dist/css");
    server.add_directory("/js", "bootstrap-4.3.1-dist/js");
    server.add_directory("/jquery", "jquery");
    server.add_directory("/image", "/home/adam/.AI/Frames");
    server.start(7777);

    return 0;
}
