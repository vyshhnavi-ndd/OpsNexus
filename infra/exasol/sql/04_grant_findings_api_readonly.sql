-- Grant the API identity only the access needed to connect and read findings.
-- Run manually as an authorized database administrator after OPSNEXUS_API exists.
-- This script does not create users, set passwords, or modify data.

GRANT CREATE SESSION TO OPSNEXUS_API;
GRANT USAGE ON SCHEMA OPS_INTEL TO OPSNEXUS_API;
GRANT SELECT ON VIEW OPS_INTEL.V_FINDINGS TO OPSNEXUS_API;
