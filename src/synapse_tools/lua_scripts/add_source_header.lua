svc_map = {}
map_file = nil
refresh_interval = nil
map_disabled = false

-- Splits the given string on spaces
function split(s)
  local result = {}
  for i in s:gmatch("%S+") do
    table.insert(result, i);
  end
  return result;
end

function log_error(err)
  core.log(core.err, '[add_source_header.lua]: ' .. err)
end

-- Loads the map from the disk:
-- We don't use haproxy's Map.new construct
-- as it does not have a programmatic interface to update
-- it, which is something we do in core.register_task
function refresh_map()
  local f = io.open(map_file)
  local tmp_map = {}
  if f ~= nil then
    for line in f:lines() do
      local parts = split(line)
      tmp_map[parts[1]] = parts[2]
    end
    svc_map = tmp_map
  end
end

function init_vars()
  map_file = os.getenv('map_file')
  if map_file == nil then
     map_disabled = true
     log_error('map_file variable not set! This will cause authentication to fail for some requests.')
   end

  refresh_interval = os.getenv('map_refresh_interval')
end

-- This is run soon after haproxy parses haproxy.cfg. We will
-- load the ip_to_svc map for the first time here.
core.register_init(function()
  xpcall(init_vars, log_error)
  xpcall(refresh_map, log_error)
end)

if map_disabled ~= true then
  -- This will register a task, to refresh the ip_to_svc map,
  -- to run every 5 seconds
  core.register_task(function()
    while true do
      xpcall(refresh_map, log_error)
      core.sleep(refresh_interval)
    end
  end)

  -- Debug endpoint for map file: this is config driven
  -- and is currently enabled for only itests
  core.register_service("map-debug", "http", function(applet)
    local response = dump(svc_map)
    applet:set_status(200)
    applet:add_header("content-length", string.len(response))
    applet:add_header("content-type", "text/plain")
    applet:start_response()
    applet:send(response)
  end)
end

-- Add source header to the request
function add_source_header(txn)
  -- First, explicitly remove any existing origin headers to avoid spoofing
  txn.http:req_del_header('X-Smartstack-Origin')

  -- Don't log if map doesn't exist or sampled out
  if (svc_map == {}) then
    return
  end

  -- Get source service
  local ip = txn.f:src()
  if ip == nil then
    ip = 'nil'
  end

  src_svc = svc_map[ip]
  if src_svc == nil then
    src_svc = '0'
  end

  -- Add header
  txn.http:req_add_header('X-Smartstack-Origin', src_svc)
end
core.register_action('add_source_header', {'http-req'}, add_source_header)

-- table to str in lua
-- not very generic, meant only for the map file (do no reuse)
function dump(o)
  local s = '{'
  for k,v in pairs(o) do
    if s ~= '{' then s = s .. ',' end
    s = s .. '"'..k..'":"' .. v .. '"'
  end
  return s .. '}'
end
