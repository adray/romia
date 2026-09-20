#pragma once
#include <string>
#include <vector>
#include <unordered_map>

#include "json.hpp"
using json = nlohmann::json;

enum class roRouteKind {
    POST,
    GET
};

struct roRoute {
    roRouteKind kind;
    std::string url;
    std::string script;
};

struct roDirectory {
    std::string url;
    std::string dir;
};

struct roGroup {
    std::string id;
    std::vector<std::string> videos;
};

struct roPath {
    std::vector<std::string> clips;
    std::vector<int> transitions;
};

struct roState {
    std::string state;
    bool loop;
    int loop_count;
    std::vector<roPath> paths;
};

struct roFSM {
    int id;
    int initial_state;
    std::string name;
    std::vector<roState> states;
};

class roServer {
    public:
        void start(const int port);
        void add_route_get(const std::string& url, const std::string& script);
        void add_route_post(const std::string& url, const std::string& script);
        void add_directory(const std::string& url, const std::string& dir);
        void load_fsm();
        void load_custom_fsm();
        void load_model();
        void load_graph();
        std::string getFSM(const int id) const;
        std::string listFSM() const;
        std::string getShow(const int id) const;
        std::string listShows() const;

    private:

        std::vector<roFSM> _fsms;
        std::vector<roGroup> _groups;
        std::vector<roRoute> _routes;
        std::vector<roDirectory> _dirs;
        //std::vector<roVideoLibrary> _library;
        std::unordered_map<std::string, int> _map;
};
