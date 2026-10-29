#!/bin/bash
# Runtime paths are read from the immutable campaign specification.
set -eo pipefail
campaign="$1"
action="$2"
config="$campaign/campaign.json"
cmssw=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["cmssw"])' "$config")
export X509_USER_PROXY
X509_USER_PROXY=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["proxy"])' "$config")
export XrdSecPROTOCOL=gsi,unix
export XRD_NETWORKSTACK=IPv4
export XRD_CONNECTIONWINDOW=30
export XRD_REQUESTTIMEOUT=120
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export PYTHONDONTWRITEBYTECODE=1
source /cvmfs/cms.cern.ch/cmsset_default.sh
cd "$cmssw/src"
eval "$(scram runtime -sh)"
if [[ "$action" == worker ]]; then
    # No interactive renewal on worker nodes. Preserve verified files on retry.
    for option in -timeleft -actimeleft; do
        remaining=$(voms-proxy-info -file "$X509_USER_PROXY" "$option")
        if (( remaining < 10800 )); then
            echo 'CMS proxy needs renewal before this batch can start.' >&2
            exit 75
        fi
    done
    exec python3 "$campaign/code/condor/scripts/c1_truth_campaign.py" worker --campaign "$campaign" --batch "$3"
fi
exec python3 "$campaign/code/condor/scripts/c1_truth_campaign.py" collect --campaign "$campaign"
