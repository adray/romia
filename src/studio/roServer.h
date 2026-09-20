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

struct roSchema {
    enum class roType {
        String,
        Number,
        Boolean,
        Array,
        Object
    };

    std::string key;
    roType type;
};

struct roFrame {
    std::string frame_file;
    std::string caption_file;
    std::string parse_status;
    std::string error;
    std::string rawText;
    double timestamp_seconds;
    json data;

    // approvals
    bool approved;
    bool autoApproved;
};

struct roVideo {
    std::string video;
    int frame_count;
    int parsed_ok;
    int parse_errors;
    std::vector<roFrame> frames;
};

struct roFrameLibrary {
    std::string frame_file;
    double timestamp_seconds;
    json data;
};

struct roVideoLibrary {
    int frame_count;
    std::string video;
    std::string primary_category;
    std::vector<roFrameLibrary> frames;
};

enum class roSearchFilter {
    All,
    PrimaryCategory,
    Clothing
};

struct roSearchResult {
    int video;
    int frame;
};

struct roGroup {
    std::string id;
    std::string image;
    std::string video;
    std::string frame;
    std::vector<std::string> videos;
};

struct roGroupMerge {
    int left;
    int right;
    double distance;
    bool approved;
    int mergeId;
};

class roServer {
    public:
        roServer() : _curGroup(0) {}

        void start(const int port);
        void add_route_get(const std::string& url, const std::string& script);
        void add_route_post(const std::string& url, const std::string& script);
        void add_directory(const std::string& url, const std::string& dir);
        void load_fsm_approvals(const std::string& filename);
        void load_approvals(const std::string& filename);

        inline const roVideo& approval(const int num) const { return _approvals[num]; }
        int numApprovals() const;
        inline int numVideos() const { return int(_approvals.size()); }
        bool isAutoApproved(const int video, const int frame) const;
        bool isApproved(const int video, const int frame) const;
        bool approve(const int video, const int frame, const std::string& jsonStr);
        const std::string getVideoJson(const int video) const;
        std::string search(const std::string& term, const roSearchFilter filter);
        std::string getNextGroupMerge();
        int approveMerge();
        int rejectMerge();
    private:
        void advanceGroup();
        void saveGroups();
        void autoApprove();
        bool validateFrame(const roFrame& frame, int* error_item) const;
        void saveApproved();
        void loadApproved();

        int _curGroup;
        std::vector<roRoute> _routes;
        std::vector<roDirectory> _dirs;
        std::vector<roVideo> _approvals;
        std::vector<roGroup> _groups;
        std::vector<roGroupMerge> _groupMerges;
        std::vector<roVideoLibrary> _library;
        std::vector<roSchema> _schema = {
            { "expression", roSchema::roType::String },
            { "clothing_type", roSchema::roType::String },
            { "clothing_color", roSchema::roType::String },
            { "clothing_style", roSchema::roType::String },
            { "clothing_pattern", roSchema::roType::String },
            { "confidence", roSchema::roType::Number },
            { "nudity", roSchema::roType::Boolean }
        };
        std::unordered_map<std::string, int> _map;
};
