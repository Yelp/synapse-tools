map = {}
map_file = nil
refresh_interval = nil

function refresh_map()
  map = Map.new(map_file, Map.str)
end

function init_vars()
  map_file = os.getenv('map_file')
  if map_file == nil then
     core.log(core.err, 'map_file variable not set! This will cause authentication to fail for some requests.')
   end

  refresh_interval = os.getenv('map_refresh_interval')
end

-- This is run soon after haproxy parses haproxy.cfg. We will
-- load the ip_to_svc map for the first time here.
core.register_init(function()
  init_vars()
  refresh_map()
end)

-- This will register a task, to refresh the ip_to_svc map,
-- to run every 5 seconds
core.register_task(function()
  while true do
    refresh_map()
    core.sleep(refresh_interval)
  end
end)

-- Add source header to the request
function add_source_header(txn)
  -- First, explicitly remove any existing origin headers to avoid spoofing
  txn.http:req_del_header('X-Smartstack-Origin')

  -- Don't log if map doesn't exist or sampled out
  if (map == {}) then
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
core.register_action('add_source_header', {'http-req'}, add_source_header)
