#include "roServer.h"
#include "Sun.h"
#include "SunScript.h"

//#define CPPHTTPLIB_OPENSSL_SUPPORT
#include "httplib.h"

#include <iostream>
#include <fstream>


struct roUserData {
    std::string contentType;
    std::string content;
    int status;
    roServer* server;
    const httplib::Request* req;
};

static int handler(SunScript::VirtualMachine* vm);

static void runProgram(const std::string& script, roUserData* userData) {
    SunScript::VirtualMachine* vm = SunScript::CreateVirtualMachine();
    unsigned char* programData = nullptr;
    unsigned char* debugData = nullptr;
    int programSize;
    int debugSize;
    std::string error;
    
    SunScript::CompileFile(script, &programData, &debugData, &programSize, &debugSize, &error);
    if (programData) {
        SunScript::SetHandler(vm, handler);
        SunScript::SetUserData(vm, userData);
        SunScript::LoadProgram(vm, programData, debugData, programSize);
        
        SunScript::RunScript(vm);
    
    } else {
        std::cout << "Compile error: " << error << std::endl;
    }

    SunScript::ShutdownVirtualMachine(vm);
}

static void serve(const httplib::Request &req, httplib::Response &res, const roRoute& route, const roServer* server) {

    roUserData userData = {"text/plain", ""};
    userData.server = const_cast<roServer*>(server);
    userData.req = &req;
    userData.status = res.status;

    runProgram(route.script, &userData);
    
    res.status = userData.status;
    res.set_content(userData.content, userData.contentType);
}

static int handler(SunScript::VirtualMachine* vm) {
    roUserData* userData = reinterpret_cast<roUserData*>(SunScript::GetUserData(vm));
    std::string callName;
    int callArgs;
    GetCallName(vm, &callName);
    GetCallNumArgs(vm, &callArgs);
    //std::cout << "Handler: " << callName << " " << callArgs << std::endl;
    if (callName == "write" && callArgs == 1) {
        std::string str;
        if (SunScript::GetParamString(vm, &str) == SunScript::VM_OK) {
            userData->content += str;
            return SunScript::VM_OK;
        }
    } else if (callName == "setContentType" && callArgs == 1) {
        std::string str;
        if (SunScript::GetParamString(vm, &str) == SunScript::VM_OK) {
            userData->contentType = str;
            return SunScript::VM_OK;
        }
    } else if (callName == "getFileToApprove" && callArgs == 1) {
        int count;
        if (SunScript::GetParamInt(vm, &count) == SunScript::VM_OK &&
            count >= 0 && count < userData->server->numVideos()) {
            const auto& approval = userData->server->approval(count);
            SunScript::PushReturnValue(vm, approval.video);
            return SunScript::VM_OK;
        }
    } else if (callName == "getFramesToApprove" && callArgs == 1) {
        int count;
        if (SunScript::GetParamInt(vm, &count) == SunScript::VM_OK &&
            count >= 0 && count < userData->server->numVideos()) {
            const auto& approval = userData->server->approval(count);
            SunScript::PushReturnValue(vm, int(approval.frames.size()));
            return SunScript::VM_OK;
        }
    } else if (callName == "getFrameFilename" && callArgs == 2) {
        int count;
        if (SunScript::GetParamInt(vm, &count) == SunScript::VM_OK &&
            count >= 0 && count < userData->server->numVideos()) {
            const auto& approval = userData->server->approval(count);

            if (SunScript::GetParamInt(vm, &count) == SunScript::VM_OK &&
                count >= 0 && count < int(approval.frames.size())) {
                SunScript::PushReturnValue(vm, approval.frames[count].frame_file);
                return SunScript::VM_OK;
            }
        }
    } else if (callName == "getNumFilesToApprove" && callArgs == 0) {
        SunScript::PushReturnValue(vm, userData->server->numApprovals());
        return SunScript::VM_OK;
    } else if (callName == "getNumVideos" && callArgs == 0) {
        SunScript::PushReturnValue(vm, userData->server->numVideos());
        return SunScript::VM_OK;
    } else if (callName == "approveFrame" && callArgs == 3) {
        int videoId;
        int frameId;
        std::string json;
        if (SunScript::GetParamInt(vm, &videoId) == SunScript::VM_OK &&
            SunScript::GetParamInt(vm, &frameId) == SunScript::VM_OK &&
            SunScript::GetParamString(vm, &json) == SunScript::VM_OK) {
            const bool approved = userData->server->approve(videoId, frameId, json);
            SunScript::PushReturnValue(vm, approved ? 1 : 0);
            return SunScript::VM_OK;
        }
    } else if (callName == "isAutoApproved" && callArgs == 2) {
        int video;
        int frame;
        if (SunScript::GetParamInt(vm, &video) == SunScript::VM_OK &&
            SunScript::GetParamInt(vm, &frame) == SunScript::VM_OK) {
            SunScript::PushReturnValue(vm, userData->server->isAutoApproved(video, frame) ? 1 : 0);
            return SunScript::VM_OK;
        }
    } else if (callName == "isApproved" && callArgs == 2) {
        int video;
        int frame;
        if (SunScript::GetParamInt(vm, &video) == SunScript::VM_OK &&
            SunScript::GetParamInt(vm, &frame) == SunScript::VM_OK) {
            SunScript::PushReturnValue(vm, userData->server->isApproved(video, frame) ? 1 : 0);
            return SunScript::VM_OK;
        }
    } else if (callName == "getArg" && callArgs == 1) {
        std::string key;
        if (SunScript::GetParamString(vm, &key) == SunScript::VM_OK) {
            SunScript::PushReturnValue(vm, userData->req->path_params.at(key));
            return SunScript::VM_OK;
        }
    } else if (callName == "getArgInt" && callArgs == 1) {
        std::string key;
        if (SunScript::GetParamString(vm, &key) == SunScript::VM_OK) {
            const std::string value = userData->req->path_params.at(key);
            SunScript::PushReturnValue(vm, std::atoi(value.c_str()));
            return SunScript::VM_OK;
        }
    } else if (callName == "hasArg" && callArgs == 1) {
        std::string key;
        if (SunScript::GetParamString(vm, &key) == SunScript::VM_OK) {
            SunScript::PushReturnValue(vm, userData->req->path_params.find(key) != userData->req->path_params.end() ? 1 : 0);
            return SunScript::VM_OK;
        }
    } else if (callName == "debugPrint" && callArgs == 1) {
        std::string text;
        if (SunScript::GetParamString(vm, &text) == SunScript::VM_OK) {
            std::cout << text << std::endl;
            return SunScript::VM_OK;
        }
    } else if (callName == "getVideoJson" && callArgs == 1) {
        int video;
        if (SunScript::GetParamInt(vm, &video) == SunScript::VM_OK) {
            const std::string json  = userData->server->getVideoJson(video);
            SunScript::PushReturnValue(vm, json);
            return SunScript::VM_OK;
        }
    } else if (callName == "search" && callArgs == 1) {
        std::string term;
        if (SunScript::GetParamString(vm, &term) == SunScript::VM_OK) {
            const std::string json  = userData->server->search(term, roSearchFilter::All);
            SunScript::PushReturnValue(vm, json);
            return SunScript::VM_OK;
        }
    } else if (callName == "getGroup" && callArgs == 0) {
        const std::string json  = userData->server->getNextGroupMerge();
        SunScript::PushReturnValue(vm, json);
        return SunScript::VM_OK;
    } else if (callName == "approveGroup" && callArgs == 0) {
        const int res  = userData->server->approveMerge();
        SunScript::PushReturnValue(vm, res);
        return SunScript::VM_OK;
    } else if (callName == "rejectGroup" && callArgs == 0) {
        const int res  = userData->server->rejectMerge();
        SunScript::PushReturnValue(vm, res);
        return SunScript::VM_OK;
    } else if (callName == "writeOK" && callArgs == 0) {
        userData->content = "{\"status\":\"ok\"}";
        return SunScript::VM_OK;
    } else if (callName == "writeError" && callArgs == 0) {
        userData->status = httplib::BadRequest_400;
        userData->content = "{\"status\":\"error\"}";
        return SunScript::VM_OK;
    } else if (callName == "getBody" && callArgs == 0) {
        const std::string body = userData->req->body;
        SunScript::PushReturnValue(vm, body);
        return SunScript::VM_OK;
    } else if (callName == "include" && callArgs == 1) {
        std::string filename;
        if (SunScript::GetParamString(vm, &filename) == SunScript::VM_OK) {
            runProgram(filename, userData);
            return SunScript::VM_OK;
        }
    }

    return SunScript::VM_ERROR;
}

void roServer::start(const int port) {
    // HTTP
    httplib::Server svr;

    for (const auto& route : _routes) {
        switch (route.kind) {
            case roRouteKind::GET:
                svr.Get(route.url, [route,this](const httplib::Request &req, httplib::Response &res) {
                    serve(req, res, route, this);
                });
            break;
            case roRouteKind::POST:
                svr.Post(route.url, [route,this](const httplib::Request &req, httplib::Response &res) {
                    serve(req, res, route, this);
                });
            break;
        }        
    }

    for (const auto& dir : _dirs) {
        svr.set_mount_point(dir.url, dir.dir);
    }

    svr.listen("0.0.0.0", port);
}

void roServer::add_route_get(const std::string& url, const std::string& script) {
    _routes.push_back({roRouteKind::GET, url, script});
}

void roServer::add_route_post(const std::string& url, const std::string& script) {
    _routes.push_back({roRouteKind::POST, url, script});
}

void roServer::add_directory(const std::string& url, const std::string& dir) {
    _dirs.push_back({url, dir});
}

//
// FSM group approvals
//

void roServer::load_fsm_approvals(const std::string& filename) {
    std::ifstream ifs(filename);
    if (!ifs.is_open()) {
        std::cerr << "Failed to open file!" << std::endl;
        return;
    }

    json data = json::parse(ifs);
    auto& groups = data["groups"];
    for (auto& group : groups.items()) {
        auto& data = _groups.emplace_back();
        data.id = group.value()["id"].get<std::string>();
        data.image = group.value()["representative"].get<std::string>();
        data.video = group.value()["video"].get<std::string>();
        data.frame = group.value()["frame"].get<std::string>();
        data.videos = group.value()["videos"].get<std::vector<std::string>>();
    }

    auto& children = data["children"];
    for (auto& child : children.items()) {
        auto& merge = _groupMerges.emplace_back();
        merge.left = child.value()["left"].get<int>();
        merge.right = child.value()["right"].get<int>();
        merge.distance = child.value()["distance"].get<double>();
    }

    saveGroups();
}

std::string roServer::getNextGroupMerge() {
    if (_curGroup >= int(_groupMerges.size())) {
        return "{}";
    }

    json result;
    json leftData;
    json rightData;

    const int count = int(_groups.size());

    auto& merge = _groupMerges[_curGroup];

    const int leftId = merge.left < count ? merge.left : _groupMerges[merge.left - count].mergeId;
    const int rightId = merge.right < count ? merge.right : _groupMerges[merge.right - count].mergeId;
    
    auto& left = _groups[leftId];
    auto& right = _groups[rightId];

    leftData["id"] = leftId;
    rightData["id"] = rightId;
    leftData["video"] = left.video;
    rightData["video"] = right.video;
    leftData["frame"] = left.frame;
    rightData["frame"] = right.frame;

    result["left"] = leftData;
    result["right"] = rightData;
    result["distance"] = merge.distance;

    return result.dump();
}

int roServer::approveMerge() {
    const int count = int(_groups.size());
    auto& merge = _groupMerges[_curGroup];
    
    merge.approved = true;

    int mergeId = merge.left;
    if (mergeId >= count) {
        mergeId = _groupMerges[mergeId - count].mergeId;
    }
    merge.mergeId = mergeId;
    _curGroup++;
    advanceGroup();
    return 1;
}

int roServer::rejectMerge() {
    _groupMerges[_curGroup].approved = false;
    _curGroup++;
    advanceGroup();
    return 1;
}

void roServer::advanceGroup() {
    const int count = int(_groups.size());

    bool advanced = true;
    while (advanced && _curGroup < int(_groupMerges.size())) {
        advanced = false;
        auto& merge = _groupMerges[_curGroup];
        if (merge.left >= count) {
            advanced |= !_groupMerges[merge.left - count].approved;
        }
        if (merge.right >= count) {
            advanced |= !_groupMerges[merge.right - count].approved;
        }
        if (advanced) {
            _curGroup++;
        }
    }

    saveGroups();
}

void roServer::saveGroups() {
    // Build groups

    const int count = int(_groups.size());
    std::vector<roGroup> groups = _groups; // Copy groups
    std::vector<bool> merged(count);
    for (auto& mergeGroup : _groupMerges) {
        if (!mergeGroup.approved) {
            continue;
        }

        auto& group = groups[mergeGroup.mergeId];
        if (mergeGroup.mergeId != mergeGroup.left) {
            const int left = mergeGroup.left < count ? mergeGroup.left : _groupMerges[mergeGroup.left - count].mergeId;
            merged[left] = true;
            for (auto& item : groups[left].videos) {
                group.videos.push_back(item);
            }
        }
        if (mergeGroup.mergeId != mergeGroup.right) {
            const int right = mergeGroup.right < count ? mergeGroup.right : _groupMerges[mergeGroup.right - count].mergeId;
            merged[right] = true;
            for (auto& item : groups[right].videos) {
                group.videos.push_back(item);
            }
        }
    }

    // Build JSON

    json data;

    for (int i = 0; i < int(groups.size()); i++) {
        const auto& group = groups[i];
        if (merged[i]) {
            continue;
        }
        json groupData;
        groupData["id"] = group.id;
        groupData["videos"] = group.videos;
        data.push_back(groupData);
    }
    
    // Save file

    const std::string dataJson = data.dump();
    std::ofstream stream("romia_fsm2.json");
    stream << dataJson << std::endl;
    stream.close();
}

//
// Approvals
//

int roServer::numApprovals() const {
    int numApprovals = 0;
    for (auto& video : _approvals) {
        for (auto& frame : video.frames) {
            if (!frame.approved) {
                numApprovals++;
                //std::cout << video.video << std::endl;
                break;
            }
        }
    }
    return numApprovals;
}

void roServer::load_approvals(const std::string& filename) {
    loadApproved();
    std::cout << "Loaded " << _library.size() << " items" << std::endl;
    
    std::ifstream ifs(filename);
    if (!ifs.is_open()) {
        std::cerr << "Failed to open file!" << std::endl;
        return;
    }

    json data = json::parse(ifs);
    auto& videos = data["videos"];
    for (auto& video : videos.items()) {
        roVideo& videoApproval = _approvals.emplace_back();
        auto& item = video.value();
        videoApproval.video = item["video"].get<std::string>();
        videoApproval.frame_count = item["frame_count"].get<int>();
        videoApproval.parsed_ok = item["parsed_ok"].get<int>();
        videoApproval.parse_errors = item["parse_errors"].get<int>();

        auto& frames = item["frames"];
        for (auto& frame : frames.items()) {
            roFrame& frameApproval = videoApproval.frames.emplace_back();
            auto& frameItem = frame.value();
            frameApproval.frame_file = frameItem["frame_file"].get<std::string>();
            frameApproval.caption_file = frameItem["caption_file"].get<std::string>();
            frameApproval.parse_status = frameItem["parse_status"].get<std::string>();
            frameApproval.timestamp_seconds = frameItem["timestamp_seconds"].get<double>();
            if (!frameItem["data"].is_null()) {
                auto& frameData = frameItem["data"];
                frameApproval.data = frameData;
            }

            if (!frameItem["error"].is_null()) {
                frameApproval.error = frameItem["error"].get<std::string>();
            }
            
            if (!frameItem["raw_text"].is_null()) {
                frameApproval.rawText = frameItem["raw_text"].get<std::string>();
            }
        }
    }

    autoApprove();
}

void roServer::autoApprove() {
    for (auto& video : _approvals) {
        for (int i = 0; i < int(video.frames.size()); i++) {
            auto& frame  = video.frames[i];
            frame.approved = false;
            frame.autoApproved = false;

            const auto& it = _map.find(video.video);
            if (it != _map.end()) {
                auto& videoLibrary = _library[it->second];
                bool found = false;
                for (const auto& frameLibrary : videoLibrary.frames) {
                    if (frame.timestamp_seconds == frameLibrary.timestamp_seconds) {
                        frame.approved = true;
                        found = true;
                        break;
                    }
                }

                if (found) {
                    continue;
                }
            }

            if (frame.parse_status != "ok") {
                continue;
            }

            //if (frame.data.confidence <= 0.7) {
            //    continue;        
            //}

            if (validateFrame(frame, nullptr)) {
                frame.approved = true;
                frame.autoApproved = true;
            }
        }
    }

    saveApproved();
}


bool roServer::validateFrame(const roFrame& frame, int* error_item) const {
    if (frame.data.is_null() ||
        !frame.data.is_object()) {
        return false;
    }

    bool ok = true;
    for (int i = 0; i < int(_schema.size()); i++) {
        auto& schema  = _schema[i];
        if (!frame.data.contains(schema.key)) {
            ok = false;
            if (error_item) {
                *error_item = i;
            }
            break;
        }

        switch (schema.type) {
            case roSchema::roType::Boolean:
                if (!frame.data[schema.key].is_boolean()) {
                    ok = false;
                }
                break;
            case roSchema::roType::Number:
                if (!frame.data[schema.key].is_number()) {
                    ok = false;
                }
                break;
            case roSchema::roType::String:
                if (!frame.data[schema.key].is_string()) {
                    ok = false;
                }
                break;
            case roSchema::roType::Array:
                if (!frame.data[schema.key].is_array()) {
                    ok = false;
                }
                break;
            case roSchema::roType::Object:
                if (!frame.data[schema.key].is_object()) {
                    ok = false;
                }
                break;
        }
        
        if (!ok) {
            if (error_item) {
                *error_item = i;
            }
            break;
        }
    }

    return ok;
}

bool roServer::isAutoApproved(const int video, const int frame) const {
    if (video < 0 || video >= int(_approvals.size())) {
        return false;
    }

    const auto& approval = _approvals[video];
    if (frame < 0 || frame >= int(approval.frames.size())) {
        return false;
    }

    return approval.frames[frame].autoApproved;
}

bool roServer::isApproved(const int video, const int frame) const {
        if (video < 0 || video >= int(_approvals.size())) {
        return false;
    }

    const auto& approval = _approvals[video];
    if (frame < 0 || frame >= int(approval.frames.size())) {
        return false;
    }

    return approval.frames[frame].approved;
}

bool roServer::approve(const int video, const int frame, const std::string& jsonStr) {
    if (video < 0 || video >= int(_approvals.size())) {
        return false;
    }

    auto& approval = _approvals[video];
    if (frame < 0 || frame >= int(approval.frames.size())) {
        return false;
    }

    json data = json::parse(jsonStr);
    roFrame frameData = approval.frames[frame];
    frameData.data = data;
    int error_item = -1;
    if (!validateFrame(frameData, &error_item)) {
        if (error_item != -1) {
             std::cout << "Error parsing: " << _schema[error_item].key << std::endl;
        }
        return false;
    }

    frameData.approved = true;
    approval.frames[frame] = frameData;
    saveApproved();
    return true;
}

const std::string roServer::getVideoJson(const int video) const {
    if (video < 0 || video >= int(_approvals.size())) {
        return "{}";
    }

    const auto& videos = _approvals[video];
    json retData = {};
    for (int i = 0; i < int(videos.frames.size()); i++) {
        const auto& frame = videos.frames[i];
        retData.push_back(frame.data);
    }

    return retData.dump();
}

void roServer::saveApproved() {
    json approved = {};
    for (auto& video : _approvals) {
        json videoFrames = {};
        bool hasFrames = false;
        for (auto& frame : video.frames) {
            if (!frame.approved) {
                continue;
            }

            json frameJson = {};
            frameJson["frame_file"] = frame.frame_file;
            frameJson["timestamp_seconds"] = frame.timestamp_seconds;
            frameJson["data"] = frame.data;

            videoFrames.push_back(frameJson);
            if (!hasFrames) {
                hasFrames = true;
            }
        }

        if (hasFrames) {
            json videoData = {};
            videoData["video"] = video.video;
            videoData["frame_count"] = video.frame_count;
            videoData["frames"] = videoFrames;
            approved.push_back(videoData);
        }
    }

    const std::string videoJson = approved.dump();
    std::ofstream stream("romia.json");
    stream << videoJson << std::endl;
    stream.close();

    loadApproved();
}

void roServer::loadApproved() {
    std::ifstream stream("romia.json");
    if (!stream.good()) {
        return;
    }

    _map.clear();
    _library.clear();

    int videoIndex = 0;
    json videos = json::parse(stream);
    for (auto& video : videos.items()) {
        auto& videoItem = _library.emplace_back();
        videoItem.video = video.value()["video"];
        videoItem.frame_count = video.value()["frame_count"];
        for (auto& frame : video.value()["frames"].items()) {
            auto& frameItem = videoItem.frames.emplace_back();
            frameItem.frame_file = frame.value()["frame_file"];
            frameItem.timestamp_seconds = frame.value()["timestamp_seconds"];
            frameItem.data = frame.value()["data"];
        }

        _map.insert(std::pair<std::string, int>(videoItem.video, videoIndex));
        videoIndex++;
    }
}

std::string roServer::search(const std::string& term, const roSearchFilter filter) {
    std::vector<roSearchResult> results;
    for (int i = 0; i <  int(_library.size()); i++) {
        auto& video = _library[i];
        for (int j = 0; j < int(video.frames.size()); j++) {
            auto& frame = video.frames[j];
            bool match = false;
            /*if ((filter == roSearchFilter::All ||
                filter == roSearchFilter::PrimaryCategory) &&
                term == frame.data.primary_category) {
                match = true;
            }*/

            /*if ((filter == roSearchFilter::All ||
                filter == roSearchFilter::Clothing) &&
                frame.data["clothing_type"].value().find(term) != std::string::npos) {
                match = true;
            }*/

            if (match) {
                results.push_back({i, j});
            }
        }
    }

    json jsonResults;
    for (auto& result : results) {
        json jsonItem;
        jsonItem["video"] = result.video;
        jsonItem["frame"] = result.frame;
        //jsonItem["clothing"] = _library[result.video].frames[result.frame].data.clothing;
        //jsonItem["primary_category"] = _library[result.video].frames[result.frame].data.primary_category;
        jsonResults.push_back(jsonItem);
    }
    return jsonResults.dump();
}
