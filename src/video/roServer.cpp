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
    } else if (callName == "getFSM" && callArgs == 2) {
        int model;
        int id;
        if (SunScript::GetParamInt(vm, &model) == SunScript::VM_OK) {
            if (SunScript::GetParamInt(vm, &id) == SunScript::VM_OK) {
                SunScript::PushReturnValue(vm, userData->server->getFSM(model, id));
                return SunScript::VM_OK;
            }
        }
    } else if (callName == "listFSM" && callArgs == 1) {
        int model;
        if (SunScript::GetParamInt(vm, &model) == SunScript::VM_OK) {
            SunScript::PushReturnValue(vm, userData->server->listFSM(model));
            return SunScript::VM_OK;
        }
    } else if (callName == "uploadAudio" && callArgs == 0) {
        std::string body = userData->req->body;
        SunScript::PushReturnValue(vm, userData->server->uploadAudio(body));
        return SunScript::VM_OK;
    } else if (callName == "getEventLatest" && callArgs == 0) {
        SunScript::PushReturnValue(vm, userData->server->getEventLatest());
        return SunScript::VM_OK;
    } else if (callName == "getEventNext" && callArgs == 1) {
        int pos;
        if (SunScript::GetParamInt(vm, &pos) == SunScript::VM_OK) {
            SunScript::PushReturnValue(vm, userData->server->getEventNext(pos));
            return SunScript::VM_OK;
        }
    } else if (callName == "getEventLatest" && callArgs == 0) {
        SunScript::PushReturnValue(vm, userData->server->getEventLatest());
        return SunScript::VM_OK;
    } else if (callName == "listModels" && callArgs == 0) {
        SunScript::PushReturnValue(vm, userData->server->listModels());
        return SunScript::VM_OK;
    } else if (callName == "postEvent" && callArgs == 0) {
        json body = json::parse(userData->req->body);
        roEvent event = {};
        if (body.contains("type") && !body["type"].is_null()) {
            event.type = body["type"];
        }
        if (body.contains("data") && !body["data"].is_null()) {
            event.data = body["data"];
        }
        if (body.contains("interrupt") && !body["interrupt"].is_null()) {
            event.interrupt = body["interrupt"];
        }
        if (body.contains("state") && !body["state"].is_null()) {
            event.state = body["state"];
        }
        SunScript::PushReturnValue(vm, userData->server->postEvent(event));
        return SunScript::VM_OK;
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

void roServer::load_models() {
    const auto& directory = std::filesystem::path("../studio/models");
    for (const auto& dir : std::filesystem::directory_iterator(directory)) {
        if (!dir.is_directory()) {
            continue;
        }
        // Check for a manifest file
        std::string manifestPath = dir.path().string() + "/manifest.json";
        if (std::filesystem::exists(manifestPath) && std::filesystem::is_regular_file(manifestPath)) {
            // Load the manifest file
            std::ifstream manifestStream(manifestPath);
            if (manifestStream.good()) {
                json manifest = json::parse(manifestStream);
                // Process the manifest as needed
                bool ok = true;
                roModel model;
                model.clipDir = manifest["clipDir"];
                model.name = manifest["name"];
                const std::string fsm_file = dir.path().string() + "/" + manifest["fsm"].get<std::string>();
                const std::string metadata_file = dir.path().string() + "/" + manifest["metadata"].get<std::string>();
                if (std::filesystem::exists(fsm_file) && std::filesystem::is_regular_file(fsm_file)) {
                    load_custom_fsm(model, fsm_file);
                } else {
                    ok = false;
                }
                if (std::filesystem::exists(metadata_file) && std::filesystem::is_regular_file(metadata_file)) {
                    load_metadata(model, metadata_file);
                } else {
                    ok = false;
                }

                if (ok) {
                    add_directory("/video/" + model.name, model.clipDir);
                    add_directory("/gan/" + model.name, dir.path().string() + "/gan/");

                    std::cout << "Loaded model: " << model.name << std::endl;
                    _models.push_back(std::move(model));
                } else {
                    std::cout << "Failed to load model: " << model.name << std::endl;
                }
            }
        }        
    }
}


void roServer::load_fsm(roModel& model, const std::string& fsm_file) {
    std::ifstream stream(fsm_file);
    if (!stream.good()) {
        return;
    }

    int index = 0;
    json groups = json::parse(stream);
    for (auto& group : groups.items()) {
        auto& groupItem = model._groups.emplace_back();
        groupItem.id = group.value()["id"];
        groupItem.videos = group.value()["videos"];

        for (auto& video : groupItem.videos) {
            model._map.insert(std::pair<std::string, int>(
                video,
                index));
        }
        index++;
    }

    for (auto& group : model._groups) {
        auto& fsm = model._fsms.emplace_back();
        fsm.name = group.id;
        fsm.id = int(model._fsms.size()) - 1;

        auto& state = fsm.states.emplace_back();
        state.state = "idle";
        state.loop = true;
        state.loop_count = 1;
    }
}

/*void roServer::load_graph() {
    std::ifstream stream("../studio/models/romia/output.json");
    if (!stream.good()) {
        return;
    }

    json videos = json::parse(stream);
    auto& graph = videos["_graph_analysis"];
    for (auto& chain : graph["chains"].items()) {
        auto& clips = chain.value();
        if (int(clips.size()) == 0) {
            continue;
        }
        const std::string& leadClip = clips[0];
        const auto& it = _map.find(leadClip);
        if (it == _map.end()) {
            continue;
        }

        auto& fsm = _fsms[it->second];
        auto& state = fsm.states.back();

        roPath& path = state.paths.emplace_back();
        for (auto& clip : clips) {
            std::string clipPath = clip;
            clipPath = clipPath.substr(0, clipPath.size() - 4);
            clipPath = "/video/" + clipPath + "frag.mp4";
            path.clips.push_back(clipPath);
        }
    }
}*/

void roServer::load_custom_fsm(roModel& model, const std::string& fsm_file) {
    std::ifstream stream(fsm_file);
    if (!stream.good()) {
        return;
    }

    json customFsm = json::parse(stream);
    for (auto& fsmItem : customFsm["fsms"].items()) {
        auto& fsm = model._fsms.emplace_back();
        fsm.name = fsmItem.value()["name"];
        fsm.initial_state = fsmItem.value()["initial_state"];
        fsm.id = int(model._fsms.size()) - 1;

        for (auto& stateItem : fsmItem.value()["states"].items()) {
            auto& state = fsm.states.emplace_back();
            state.state = stateItem.value()["name"];
            state.loop = stateItem.value()["loop"];
            state.loop_count = stateItem.value()["loop_count"];

            for (auto& pathItem : stateItem.value()["paths"].items()) {
                roPath& path = state.paths.emplace_back();
                for (auto& clip : pathItem.value()["clips"]) {
                    std::string clipPath = clip;
                    clipPath = clipPath.substr(0, clipPath.size() - 4);
                    clipPath = "/video/" + model.name + "/" + clipPath + "frag.mp4";
                    path.clips.push_back(clipPath);
                }
                for (auto& transition : pathItem.value()["transition"]) {
                    path.transitions.push_back(transition);
                }
            }
        }
    }
}

void roServer::load_metadata(roModel& model, const std::string& metadata_file) {
    std::ifstream stream(metadata_file);
    if (!stream.good()) {
        return;
    }

    json metadata = json::parse(stream);
    for (auto& item : metadata.items()) {
        const std::string key = item.key();
        const std::string file = "/video/" + model.name + "/" + key.substr(0, key.size() - 4) + "frag.mp4";
        auto& data = model._metadata[file];
        data.file = key;
        if (item.value().contains("duration")) {
            data.duration = item.value()["duration"];
        } else {
            data.duration = 5062.5; // 81 frames at 16fps
        }
    }
}

std::string roServer::listFSM(const int model) const {
    if (model < 0 || model >= static_cast<int>(_models.size())) {
        return "{}";
    }

    json list;
    json items;

    for (auto& fsm : _models[model]._fsms) {
        json data;
        data["id"] = fsm.id;
        data["name"] = fsm.name;
        data["num_states"] = int(fsm.states.size());
        items.push_back(data);
    }
    list["items"] = items;
    list["default"] = 0;
    return list.dump();
}

std::string roServer::getFSM(const int model, const int id) const {
    if (model < 0 || model >= static_cast<int>(_models.size()) || id < 0 ||
        id >= static_cast<int>(_models[model]._fsms.size())) {
        return "{}";
    }

    json fsm;

    for (auto& state : _models[model]._fsms[id].states) {
        json stateJson;
        stateJson["state"] = state.state;
        stateJson["loop"] = state.loop;
        stateJson["loop_count"] = state.loop_count;

        json paths;
        for (auto& path : state.paths) {
            json pathJson;
            json clipsJson;
            for (auto& clip : path.clips) {
                json clipJson;
                clipJson["file"] = clip;
                const auto it = _models[model]._metadata.find(clip);
                if (it != _models[model]._metadata.end()) {
                    clipJson["duration"] = it->second.duration;
                } else {
                    clipJson["duration"] = 5062.5; // 81 frames at 16fps
                    std::cerr << "Warning: Metadata for clip " << clip << " not found. Using default duration." << std::endl;
                }
                clipsJson.push_back(clipJson);
            }
            pathJson["clips"] = clipsJson;
            json transitionsJson;
            for (auto& transition : path.transitions) {
                transitionsJson.push_back(transition);
            }
            pathJson["transitions"] = transitionsJson;
            paths.push_back(pathJson);
        }
        stateJson["paths"] = paths;

        fsm.push_back(stateJson);
    }

    return fsm.dump();
}


std::string roServer::uploadAudio(const std::string& body) {
    // Save the uploaded video to the appropriate directory
    // and return an ID for the uploaded video.

    json response;

    const int id = _audioQueue.tail.fetch_add(1);
    
    const std::string audioPath = "audio/audio_" + std::to_string(id);
    std::fstream file(audioPath, std::ios::out | std::ios::binary);
    if (file.is_open()) {
        file.write(body.data(), body.size());
        file.close();
    } else {
        response["status"] = "error";
        return response.dump();
    }

    response["audio"] = audioPath;
    response["status"] = "ok";
    return response.dump();
}


std::string roServer::postEvent(const roEvent& event){ 
    if (event.type != "audio" && event.type != "update" && event.type != "fsm" && event.type != "subtitle") {
        json response;
        response["status"] = "error";
        response["message"] = "Invalid event type";
        return response.dump();
    }

    if (event.type == "audio" && event.data.empty()) {
        json response;
        response["status"] = "error";
        response["message"] = "Audio event must have data";
        return response.dump();
    }
    
    if (event.type == "subtitle" && event.data.empty()) {
        json response;
        response["status"] = "error";
        response["message"] = "Subtitle event must have data";
        return response.dump();
    }

    if (event.type == "fsm" && event.data.empty()) {
        json response;
        response["status"] = "error";
        response["message"] = "FSM event must have data";
        return response.dump();
    }

    {
        std::lock_guard<std::mutex> lock(_eventsMutex);
        _events.push_back(event);
    }
    json response;
    response["status"] = "ok";
    return response.dump();
}

std::string roServer::getEventNext(const int pos) const {
    std::lock_guard<std::mutex> lock(_eventsMutex);
    int id = pos;

    json response;
    json events;

    if (id < 0 || id >= static_cast<int>(_events.size())) {
        return "{\"status\":\"no_new_event\"}"; // No new event
    }
    while (id < static_cast<int>(_events.size())) {
        const auto& event = _events[id];
        json eventJson;
        eventJson["type"] = event.type;
        eventJson["data"] = event.data;
        eventJson["interrupt"] = event.interrupt;
        eventJson["state"] = event.state;
        events.push_back(eventJson);
        id++;
    }
    response["events"] = events;
    response["next_id"] = id;
    response["status"] = "ok";
    return response.dump();
}

std::string roServer::getEventLatest() const {
    std::lock_guard<std::mutex> lock(_eventsMutex);
    json response;
    response["next_id"] = static_cast<int>(_events.size());
    response["status"] = "ok";
    return response.dump();
}

std::string roServer::listModels() const {
    json response;
    json models;
    for (int i = 0; i < static_cast<int>(_models.size()); i++) {
        const auto& model = _models[i];
        json modelJson;
        modelJson["id"] = i;
        modelJson["name"] = model.name;
        models.push_back(modelJson);
    }
    response["models"] = models;
    response["status"] = "ok";
    return response.dump();
}
