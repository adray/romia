#pragma once
#include <string>
#include <vector>
#include <unordered_map>
#include <atomic>
#include <mutex>

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

struct roMetadata {
    std::string file;
    double duration;
};

struct roModel {
    std::string name;
    std::string clipDir;
    std::vector<roFSM> _fsms;
    std::vector<roGroup> _groups;
    std::unordered_map<std::string, roMetadata> _metadata;
    std::unordered_map<std::string, int> _map;
};

struct roAudioQueue {
    std::atomic<int> tail;

    roAudioQueue() : tail(0) {}
};

struct roEvent {
    std::string type;
    std::string data;
    std::string state;
    bool interrupt;
};

class roServer {
    public:
        void start(const int port);
        void add_route_get(const std::string& url, const std::string& script);
        void add_route_post(const std::string& url, const std::string& script);
        void add_directory(const std::string& url, const std::string& dir);
        void load_models();
        std::string getFSM( const int model, const int id) const;
        std::string listFSM(const int model) const;
        std::string listModels() const;
    
        std::string uploadAudio(const std::string& body);

        std::string postEvent(const roEvent& event);
        std::string getEventNext(const int pos) const;
        std::string getEventLatest() const;

    private:
        void load_custom_fsm(roModel& model, const std::string& fsm_file);
        void load_metadata(roModel& model, const std::string& metadata_file);
        void load_fsm(roModel& model, const std::string& fsm_file);

        /*void load_graph();*/

        roAudioQueue _audioQueue;
        mutable std::mutex _eventsMutex;
        std::vector<roModel> _models;
        std::vector<roRoute> _routes;
        std::vector<roEvent> _events;
        std::vector<roDirectory> _dirs;
};
