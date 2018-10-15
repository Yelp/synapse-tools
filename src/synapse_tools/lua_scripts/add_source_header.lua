map = {}
map_file = ''

-- Get the path to the haproxy.cfg file
function get_config_filename(cmdline)
  local found = false
  for s in string.gmatch(cmdline, '%g+') do
    if s == '-f' then
      found = true
    elseif found then
      return s
    end
  end
end

-- Get the map_file path from haproxy.cfg's global stanza
function get_map_file(config_file)
   fh, err = io.open(config_file)
   if err then
     core.log(core.err, 'Cannot open the map file at ' .. config_file .. '. This will cause service authentication to fail!')
   end

  while true do
     ln = fh:read()
    if ln == nil then break end
    if ln:find('setenv map_file') then
       return ln:match('%S+/.*$')
    end
  end
end

-- Get the cmdline used to run the haproxy process, because this cmdline
-- will also have the path to haproxy.cfg
function get_cmdline()
  local f = io.open('/proc/self/cmdline', "rb")
  local cmdline = f:read("*all")
  f:close()

  return cmdline
end

function refresh_map()
  map = Map.new(map_file, Map.str)
end

-- This is run soon after haproxy parses haproxy.cfg. We will
-- load the ip_to_svc map for the first time here.
core.register_init(function()
  local cmdline = get_cmdline()
  local config_file = get_config_filename(cmdline)
  map_file = get_map_file(config_file)

  refresh_map()
end)

-- This will register a task, to refresh the ip_to_svc map,
-- to run every 5 seconds
core.register_task(function()
  while true do
    refresh_map()
    core.sleep(5)
  end
end)

-- Add source header to the request
function add_source_header(txn)
  -- First, explicitly remove any existing origin headers to avoid spoofing
  txn.http:req_del_header('X-Smartstack-Origin')

  -- Don't log if map doesn't exist or sampled out
  if (map == nil) then
    return
  end

  -- Get source service
  local ip = txn.f:src()
  if ip == nil then
    ip = 'nil'
  end

  src_svc = map:lookup(ip)
  if src_svc == nil then
    src_svc = '0'
  end

  -- Add header
  txn.http:req_add_header('X-Smartstack-Origin', src_svc)
end
core.register_action('add_source_header', {'tcp-req', 'http-req'}, add_source_header)
