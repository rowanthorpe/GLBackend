# Ahmia integration format

Ahmia.fi is a service crawling and indexing hidden service network. Due to
the anonymous nature of the darknets, a node can be unreachable if want to be so. 
Methodology for promote the descriptions of hidden service has been invented
or implemented by ahmia, and we're going to support integration.

## description.json

description.json is one of the files automatically looked by ahmia crawler, 
other are robots.txt and (and ?).

this is the format of description.json file:

"title"
"description" 
"keywords"
"relation" 
"language" 
"contactInformation" 
"type"

### GL proposal

add also the field "application", able to specify which kinf ofg software is hanidling the hidden service (can be generic like "http server" or detailed)

we've proposed then:

"application": "GlobaLeaks"

# Ahmia HS push interface
