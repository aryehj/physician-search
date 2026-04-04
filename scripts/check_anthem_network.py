# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "python-dotenv"]
# ///
"""
Stage 3: Filter physicians to Cook County, IL and check Anthem in-network status.

Reads:   data/physicians.json  (from lookup_npis.py)
         .env                  (Anthem API credentials)
Outputs: data/in_network_physicians.json
         data/in_network_physicians.csv

Usage: uv run check_anthem_network.py

Adapting for a different insurer:
- Set the four env vars in .env to point to your insurer's FHIR endpoint
- The OAuth2 flow (client credentials grant) is standard; if your insurer
  uses a different auth method, modify get_access_token()
- The FHIR Practitioner/PractitionerRole queries follow the DaVinci Plan-Net IG;
  any insurer implementing this IG should work with minimal changes
- The COOK_COUNTY_CITIES filter (used only in standalone mode) should be
  replaced with your geographic area of interest
"""

import csv
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

# --- Configuration -----------------------------------------------------------

ANTHEM_CLIENT_ID = os.environ.get("ANTHEM_CLIENT_ID")
ANTHEM_CLIENT_SECRET = os.environ.get("ANTHEM_CLIENT_SECRET")
ANTHEM_TOKEN_URL = os.environ.get("ANTHEM_ACCESS_TOKEN_URL")
FHIR_BASE = os.environ.get("ANTHEM_PROVIDER_DIRECTORY_URL")

# CUSTOMIZE: Replace with municipalities in your geographic area of interest.
# This set is only used by main() in standalone mode; when called from main.py,
# the geographic filter is handled by the caller.
# Current default: Cook County, IL municipalities (not exhaustive — add as needed)
# Source: Cook County Clerk's office municipality list
COOK_COUNTY_CITIES = {
    # Chicago
    "CHICAGO",
    # North Shore / North suburbs
    "EVANSTON", "SKOKIE", "WILMETTE", "WINNETKA", "KENILWORTH", "GLENCOE",
    "NORTHBROOK", "GLENVIEW", "GOLF", "MORTON GROVE", "NILES", "LINCOLNWOOD",
    "PARK RIDGE", "DES PLAINES", "MOUNT PROSPECT", "ARLINGTON HEIGHTS",
    "PROSPECT HEIGHTS", "WHEELING", "NORTHFIELD", "TECHNY",
    # West suburbs
    "OAK PARK", "RIVER FOREST", "FOREST PARK", "MAYWOOD", "MELROSE PARK",
    "BELLWOOD", "BROADVIEW", "WESTCHESTER", "HILLSIDE", "BERKELEY",
    "ELMWOOD PARK", "RIVER GROVE", "FRANKLIN PARK", "SCHILLER PARK",
    "NORRIDGE", "HARWOOD HEIGHTS", "ELK GROVE VILLAGE",
    # Southwest suburbs
    "CICERO", "BERWYN", "STICKNEY", "LYONS", "RIVERSIDE", "BROOKFIELD",
    "LA GRANGE", "LA GRANGE PARK", "WESTERN SPRINGS", "INDIAN HEAD PARK",
    "COUNTRYSIDE", "HODGKINS", "MCCOOK", "SUMMIT", "JUSTICE", "BRIDGEVIEW",
    "HICKORY HILLS", "PALOS HILLS", "PALOS HEIGHTS", "PALOS PARK",
    "ORLAND PARK", "ORLAND HILLS", "TINLEY PARK", "OAK FOREST",
    "MIDLOTHIAN", "OAK LAWN", "HOMETOWN", "CHICAGO RIDGE", "WORTH",
    "ALSIP", "CRESTWOOD", "ROBBINS", "BLUE ISLAND", "EVERGREEN PARK",
    "BURBANK", "BEDFORD PARK",
    # South suburbs
    "HARVEY", "DOLTON", "SOUTH HOLLAND", "THORNTON", "LANSING",
    "CALUMET CITY", "BURNHAM", "LYNWOOD", "HOMEWOOD", "FLOSSMOOR",
    "OLYMPIA FIELDS", "MATTESON", "RICHTON PARK", "PARK FOREST",
    "CHICAGO HEIGHTS", "STEGER", "SOUTH CHICAGO HEIGHTS", "SAUK VILLAGE",
    "FORD HEIGHTS", "DIXMOOR", "POSEN", "MARKHAM", "HAZEL CREST",
    "COUNTRY CLUB HILLS", "EAST HAZEL CREST",
    # Northwest suburbs (Cook County portions)
    "PALATINE", "ROLLING MEADOWS", "HOFFMAN ESTATES", "SCHAUMBURG",
    "HANOVER PARK", "STREAMWOOD", "BARTLETT", "BARRINGTON",
    "INVERNESS", "BUFFALO GROVE", "ROSEMONT",
}

DATA_DIR = Path("data")


def get_access_token(client: httpx.Client) -> str:
    """Obtain OAuth2 access token via client credentials grant."""
    resp = client.post(
        ANTHEM_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        auth=(ANTHEM_CLIENT_ID, ANTHEM_CLIENT_SECRET),
    )
    resp.raise_for_status()
    token_data = resp.json()
    return token_data["access_token"]


def search_practitioner(
    client: httpx.Client, token: str, last_name: str, first_name: str
) -> list[dict]:
    """Search the FHIR Practitioner resource by name."""
    first = first_name.split()[0] if first_name else ""
    if not first or not last_name:
        return []

    resp = client.get(
        f"{FHIR_BASE}/Practitioner",
        params={"family": last_name, "given": first},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/fhir+json",
        },
    )

    if resp.status_code == 401:
        print("    [!] Access token expired or invalid")
        return []
    if resp.status_code != 200:
        print(f"    [!] Practitioner search returned {resp.status_code}")
        return []

    bundle = resp.json()
    return bundle.get("entry", [])


def extract_npi_from_resource(resource: dict) -> str | None:
    """Pull the NPI from a FHIR Practitioner resource's identifier list."""
    for ident in resource.get("identifier", []):
        system = ident.get("system", "")
        if "npi" in system.lower() or "us-npi" in system:
            return ident.get("value")
    return None


def find_practitioner_by_npi(entries: list[dict], target_npi: str) -> dict | None:
    """Find the FHIR Practitioner entry whose NPI matches."""
    for entry in entries:
        resource = entry.get("resource", {})
        npi = extract_npi_from_resource(resource)
        if npi == target_npi:
            return resource
    return None


def get_practitioner_roles(
    client: httpx.Client, token: str, practitioner_id: str
) -> list[dict]:
    """Fetch PractitionerRole resources linked to a Practitioner."""
    resp = client.get(
        f"{FHIR_BASE}/PractitionerRole",
        params={"practitioner": practitioner_id},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/fhir+json",
        },
    )
    if resp.status_code != 200:
        return []
    bundle = resp.json()
    return [e.get("resource", {}) for e in bundle.get("entry", [])]


def run(physicians: list[dict]) -> list[dict]:
    """Check physicians against Anthem directory. Returns enriched in-network list."""
    with httpx.Client(timeout=30.0) as client:
        print("\n=== Authenticating with Anthem ===")
        try:
            token = get_access_token(client)
            print("  Got access token")
        except httpx.HTTPStatusError as e:
            print(f"  Failed to get token: {e.response.status_code}")
            print(f"  Response: {e.response.text[:500]}")
            raise
        except Exception as e:
            print(f"  Failed to get token: {e}")
            raise

        # Check each physician against the provider directory
        print(f"\n=== Checking {len(physicians)} physicians against Anthem directory ===")
        in_network = []
        not_found = []

        for i, phys in enumerate(physicians):
            first = phys.get("fore_name") or phys.get("first_name", "")
            name = f"{first} {phys['last_name']}"
            npi = phys["npi"]
            print(f"  [{i + 1}/{len(physicians)}] {name} (NPI {npi})...", end=" ", flush=True)

            entries = search_practitioner(client, token, phys["last_name"], first)

            if not entries:
                print("not in directory")
                not_found.append(phys)
                time.sleep(0.4)
                continue

            match = find_practitioner_by_npi(entries, str(npi))
            if match:
                # Found in directory by NPI — this means in-network
                practitioner_id = match.get("id", "")
                roles = get_practitioner_roles(client, token, practitioner_id)

                network_names = []
                network_org_ids = []
                role_specialties = []
                role_locations = []
                accepting_patients = False
                for role in roles:
                    # Standard network field (usually empty in this API)
                    for net in role.get("network", []):
                        ref = net.get("display") or net.get("reference", "")
                        if ref and ref not in network_names:
                            network_names.append(ref)

                    # DaVinci extensions — where Anthem actually puts network data
                    for ext in role.get("extension", []):
                        ext_url = ext.get("url", "")

                        # network-reference extension
                        if "network-reference" in ext_url:
                            val = ext.get("valueReference", {})
                            display_name = val.get("display", "")
                            org_id = val.get("reference", "")
                            if display_name and display_name not in network_names:
                                network_names.append(display_name)
                            if org_id and org_id not in network_org_ids:
                                network_org_ids.append(org_id)

                        # newpatients extension (nested)
                        if "newpatients" in ext_url:
                            for sub in ext.get("extension", []):
                                if sub.get("url") == "acceptingPatients":
                                    code = (sub.get("valueCodeableConcept", {})
                                            .get("coding", [{}])[0]
                                            .get("code", ""))
                                    if code == "newpt":
                                        accepting_patients = True
                                if sub.get("url") == "fromNetwork":
                                    val = sub.get("valueReference", {})
                                    display_name = val.get("display", "")
                                    if display_name and display_name not in network_names:
                                        network_names.append(display_name)

                        # qualification extension — specialties
                        if "qualification" in ext_url:
                            for sub in ext.get("extension", []):
                                if sub.get("url") == "code":
                                    for coding in (sub.get("valueCodeableConcept", {})
                                                   .get("coding", [])):
                                        desc = coding.get("display", "")
                                        if desc and desc not in role_specialties:
                                            role_specialties.append(desc)

                    # Standard specialty field
                    for spec in role.get("specialty", []):
                        for coding in spec.get("coding", []):
                            desc = coding.get("display", "")
                            if desc and desc not in role_specialties:
                                role_specialties.append(desc)

                    # Locations
                    for loc in role.get("location", []):
                        ref = loc.get("display") or loc.get("reference", "")
                        if ref and ref not in role_locations:
                            role_locations.append(ref)

                record = {
                    **phys,
                    "anthem_practitioner_id": practitioner_id,
                    "anthem_networks": network_names,
                    "anthem_network_org_ids": network_org_ids,
                    "anthem_specialties": role_specialties,
                    "anthem_locations": role_locations,
                    "accepting_new_patients": accepting_patients,
                    "in_directory": True,
                }
                in_network.append(record)
                print(f"IN DIRECTORY — {len(roles)} role(s)")
            else:
                print(f"name matched ({len(entries)} result(s)) but NPI mismatch")
                not_found.append(phys)

            time.sleep(0.4)  # rate limit

    # Summary
    print(f"\n=== Summary ===")
    print(f"  Physicians checked:        {len(physicians)}")
    print(f"  Found in Anthem directory: {len(in_network)}")
    print(f"  Not found:                 {len(not_found)}")

    # Print results
    print(f"\n=== In-Network Physicians ({len(in_network)}) ===")
    for p in sorted(in_network, key=lambda x: -x.get("article_count", 0)):
        nets = ", ".join(p.get("anthem_networks", [])) or "network info unavailable"
        accepting = "accepting new patients" if p.get("accepting_new_patients") else "not confirmed accepting"
        city = p.get("practice_city") or p.get("city") or "?"
        state = p.get("practice_state") or p.get("state") or "?"
        first = p.get("fore_name") or p.get("first_name", "")
        name = f"{first} {p['last_name']}"
        print(
            f"  {name}, {p.get('credential') or '?'} "
            f"— {p.get('specialty', '?')} — {city}, {state} "
            f"— {p.get('article_count', 0)} pub(s) — {nets} — {accepting}"
        )

    return in_network


def main():
    # Validate env vars
    missing = []
    for var in [
        "ANTHEM_CLIENT_ID", "ANTHEM_CLIENT_SECRET",
        "ANTHEM_ACCESS_TOKEN_URL", "ANTHEM_PROVIDER_DIRECTORY_URL",
    ]:
        if not os.environ.get(var):
            missing.append(var)
    if missing:
        print(f"Error: missing environment variables: {', '.join(missing)}")
        print("Make sure your .env file has all four Anthem credentials.")
        sys.exit(1)

    # Load physicians
    physicians_path = DATA_DIR / "physicians.json"
    if not physicians_path.exists():
        print("Error: data/physicians.json not found. Run lookup_npis.py first.")
        sys.exit(1)

    with open(physicians_path) as f:
        physicians = json.load(f)
    print(f"Loaded {len(physicians)} physician records")

    # Filter to Cook County, IL
    cook_county = [
        p for p in physicians
        if p.get("practice_state") == "IL"
        and p.get("practice_city", "").upper() in COOK_COUNTY_CITIES
        and p.get("npi")  # must have an NPI to look up
    ]
    print(f"Filtered to {len(cook_county)} physicians in Cook County, IL with NPIs")

    if not cook_county:
        print("No physicians match the Cook County filter. Nothing to check.")
        sys.exit(0)

    try:
        in_network = run(cook_county)
    except Exception:
        sys.exit(1)

    if not in_network:
        print("\nNo in-network physicians found. Results not saved.")
        sys.exit(0)

    # Save JSON
    json_path = DATA_DIR / "in_network_physicians.json"
    with open(json_path, "w") as f:
        json.dump(in_network, f, indent=2)
    print(f"\nSaved {json_path}")

    # Save CSV
    csv_path = DATA_DIR / "in_network_physicians.csv"
    fieldnames = [
        "last_name", "fore_name", "article_count", "npi", "credential",
        "specialty", "practice_city", "practice_state", "practice_address",
        "anthem_networks", "anthem_specialties", "anthem_locations",
        "accepting_new_patients",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for p in in_network:
            row = {
                **p,
                "anthem_networks": "; ".join(p.get("anthem_networks", [])),
                "anthem_specialties": "; ".join(p.get("anthem_specialties", [])),
                "anthem_locations": "; ".join(p.get("anthem_locations", [])),
            }
            writer.writerow(row)
    print(f"Saved {csv_path}")


def probe(resource: str, params: dict | None = None):
    """Diagnostic: fetch a FHIR resource and dump the raw JSON."""
    load_dotenv()
    with httpx.Client(timeout=30.0) as client:
        token = get_access_token(client)
        resp = client.get(
            f"{FHIR_BASE}/{resource}",
            params=params or {},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/fhir+json",
            },
        )
        print(f"GET {resource} — {resp.status_code}")
        print(json.dumps(resp.json(), indent=2)[:5000])


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--probe":
        # Usage: uv run check_anthem_network.py --probe PractitionerRole practitioner=<id>
        resource = sys.argv[2] if len(sys.argv) > 2 else "PractitionerRole"
        params = {}
        for arg in sys.argv[3:]:
            if "=" in arg:
                k, v = arg.split("=", 1)
                params[k] = v
        probe(resource, params)
    else:
        main()
