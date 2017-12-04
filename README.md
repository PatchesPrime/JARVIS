# JARVIS
[J]*ust* [A]*nother* [R]*ather* [V]*ery* [I]*gnorant* [S]*ystem*

JARVIS is a bot developed for use by my friends and I on XMPP. It started as just a weather alert bot, and progressed from there.
Internally he uses a MongoDB server for dealing with data persistence. One day I'll detail its 'schema' here in the unlikely event someone wants to run their own JARVIS.

***
### Features
   * Alert of active weather alerts directly from NWS (filtered by severity).
   * Poll the GitHub API for monitoring for new commits.
   * Manage user accounts on the XMPP server we own.


***
### Use XMPP and like JARVIS?
JARVIS is technically capable of handling all the features listed above for anyone who uses XMPP as we do. He only listens to subscribers/admin for most things, but just being his friend will get you free game notifications. His JID: jarvis@hive.nullcorp.org

***
### Forking
JARVIS requires a few thing to operate, namely some API keys and a MongoDB instance. I intend to remove the MongoDB requirement, however he will still require some API keys (for GitHub for example). It's a pain, but not a huge one. May change in future.

Create a 'config.py' in his root directory with the following:
``` python
xmpp_user = 'JID here'
xmpp_pass = 'password here'
mongo_user = 'jarvis'
mongo_pass = 'mongo pass here'
geocode_key = 'google geocode api key'
restapi_key = 'xmpp server rest api key'
github = 'github api key'
```
