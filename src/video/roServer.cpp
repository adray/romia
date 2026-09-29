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
    } else if (callName == "getFSM" && callArgs == 1) {
        int id;
        if (SunScript::GetParamInt(vm, &id) == SunScript::VM_OK) {
            SunScript::PushReturnValue(vm, userData->server->getFSM(id));
            return SunScript::VM_OK;
        }
    } else if (callName == "listFSM" && callArgs == 0) {
        SunScript::PushReturnValue(vm, userData->server->listFSM());
        return SunScript::VM_OK;
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
    } else if (callName == "postEvent" && callArgs == 0) {
        json body = json::parse(userData->req->body);
        roEvent event;
        event.type = body["type"];
        if (body.contains("data") && !body["data"].is_null()) {
            event.data = body["data"];
        }
        event.interrupt = body["interrupt"];
        event.state = body["state"];
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

void roServer::load_fsm() {
    std::ifstream stream("../studio/models/romia/romia_fsm.json");
    if (!stream.good()) {
        return;
    }

    int index = 0;
    json groups = json::parse(stream);
    for (auto& group : groups.items()) {
        auto& groupItem = _groups.emplace_back();
        groupItem.id = group.value()["id"];
        groupItem.videos = group.value()["videos"];

        for (auto& video : groupItem.videos) {
            _map.insert(std::pair<std::string, int>(
                video,
                index));
        }
        index++;
    }

    for (auto& group : _groups) {
        auto& fsm = _fsms.emplace_back();
        fsm.name = group.id;
        fsm.id = int(_fsms.size()) - 1;

        auto& state = fsm.states.emplace_back();
        state.state = "idle";
        state.loop = true;
        state.loop_count = 1;
    }
}

void roServer::load_graph() {
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
}

void roServer::load_custom_fsm() {
    std::ifstream stream("../studio/models/romia/romia_custom_fsm.json");
    if (!stream.good()) {
        return;
    }

    json customFsm = json::parse(stream);
    for (auto& fsmItem : customFsm["fsms"].items()) {
        auto& fsm = _fsms.emplace_back();
        fsm.name = fsmItem.value()["name"];
        fsm.initial_state = fsmItem.value()["initial_state"];
        fsm.id = int(_fsms.size()) - 1;

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
                    clipPath = "/video/" + clipPath + "frag.mp4";
                    path.clips.push_back(clipPath);
                }
                for (auto& transition : pathItem.value()["transition"]) {
                    path.transitions.push_back(transition);
                }
            }
        }
    }
}


std::string roServer::listFSM() const {
    json list;
    json items;

    for (auto& fsm : _fsms) {
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

std::string roServer::getFSM(const int id) const {
    json fsm;

    for (auto& state : _fsms[id].states) {
        json stateJson;
        stateJson["state"] = state.state;
        stateJson["loop"] = state.loop;
        stateJson["loop_count"] = state.loop_count;

        json paths;
        for (auto& path : state.paths) {
            json pathJson;
            json clipsJson;
            for (auto& clip : path.clips) {
                clipsJson.push_back(clip);
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

    const int id = _audioQueue.tail;
    _audioQueue.tail++;
    
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
    if (event.type != "audio" && event.type != "update") {
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

    _events.push_back(event);
    json response;
    response["status"] = "ok";
    return response.dump();
}

std::string roServer::getEventNext(const int pos) const {
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
    json response;
    response["next_id"] = static_cast<int>(_events.size());
    response["status"] = "ok";
    return response.dump();
}
