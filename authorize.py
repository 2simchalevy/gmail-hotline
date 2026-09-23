"""
authorize.py

No longer needed for the cloud deployment. Authorization now happens by
visiting the /authorize URL on your running server (Cloud Run or local)
in any web browser — see server.py.

This file is kept only as a pointer in case you find it while poking
around; there's nothing to run here.
"""

if __name__ == "__main__":
    print(
        "Authorization is now done through your browser instead of this "
        "script. Once the server is deployed, visit:\n\n"
        "    https://<your-service-url>/authorize\n\n"
        "and follow the Google consent screen."
    )
