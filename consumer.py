''' Consumer for OpenSUIC - Southern Illinios University '''
from __future__ import unicode_literals

import os
import time

from lxml import etree

from datetime import date, timedelta

import requests

from nameparser import HumanName

from dateutil.parser import *

from scrapi.linter import lint
from scrapi.linter.document import RawDocument, NormalizedDocument

NAME = 'opensiuc'
OAI_DC_BASE = 'http://opensiuc.lib.siu.edu/do/oai/'

NAMESPACES = {'dc': 'http://purl.org/dc/elements/1.1/', 
            'oai_dc': 'http://www.openarchives.org/OAI/2.0/',
            'ns0': 'http://www.openarchives.org/OAI/2.0/'}

DEFAULT_ENCODING = 'UTF-8'

record_encoding = None

# load the list of approved series_names as a file - second option
with open(os.path.join(os.path.dirname(__file__), 'approved_sets.txt')) as series_names:
    series_name_list = [word.replace('\n', '') for word in series_names]

def copy_to_unicode(element):

    encoding = record_encoding or DEFAULT_ENCODING
    element = ''.join(element)
    if isinstance(element, unicode):
        return element
    else:
        return unicode(element, encoding=encoding)
    
def consume(days_back=1):
    start_date = date.today() - timedelta(days_back)
    base_url = OAI_DC_BASE + '?verb=ListRecords&metadataPrefix=oai_dc&from='
    url = base_url + str(start_date) + 'T00:00:00Z'

    num_approved_records = 0
    num_rejected_records = 0
    approved_sets = []
    rejected_sets = []

    records = get_records(url)

    xml_list = []
    for record in records:
        set_spec = record.xpath('ns0:header/ns0:setSpec/node()', namespaces=NAMESPACES)[0]
        doc_id = record.xpath('ns0:header/ns0:identifier/node()', namespaces=NAMESPACES)[0]

        set_spec = record.xpath('ns0:header/ns0:setSpec/node()', namespaces=NAMESPACES)[0]

        record_string = etree.tostring(record, encoding=record_encoding)

        if set_spec.replace('publication:', '') in series_name_list:
            approved_sets.append(set_spec)
            num_approved_records += 1
        else:
            rejected_sets.append(set_spec)
            num_rejected_records += 1

        xml_list.append(RawDocument({
                    'doc': record_string,
                    'source': NAME,
                    'docID': copy_to_unicode(doc_id),
                    'filetype': 'xml'
                }))

    print "There were {} approved sets".format(num_approved_records)
    print "The records were from these approved sets: {}".format(set(approved_sets))
    print "There were {} rejected sets".format(num_rejected_records)
    print "The records were from these rejected sets: {}".format(set(rejected_sets))

    return xml_list

def get_records(url):
    data = requests.get(url)
    record_encoding = data.encoding
    doc = etree.XML(data.content)
    records = doc.xpath('//ns0:record', namespaces=NAMESPACES)
    token = doc.xpath('//ns0:resumptionToken/node()', namespaces=NAMESPACES)

    if len(token) == 1:
        time.sleep(0.5)
        base_url = OAI_DC_BASE + '?verb=ListRecords&resumptionToken=' 
        url = base_url + token[0]
        records += get_records(url)

    return records

    # TODO: fix if there are no records found... what would the XML look like?

def get_properties(record):

    all_ids = record.xpath('//dc:identifier/node()', namespaces=NAMESPACES)
    pdf = ''
    for identifier in all_ids:
        if 'cgi/viewcontent' in identifier:
            pdf = identifier
    properties = {}
    properties['set_spec'] = record.xpath('ns0:header/ns0:setSpec/node()', namespaces=NAMESPACES)[0]
    properties['publisher'] = (record.xpath('//dc:publisher/node()', namespaces=NAMESPACES) or [''])[0]
    properties['source'] = (record.xpath('//dc:source/node()', namespaces=NAMESPACES) or [''])[0]
    properties['type'] = (record.xpath('//dc:type/node()', namespaces=NAMESPACES) or [''])[0]
    properties['format'] = (record.xpath('//dc:format/node()', namespaces=NAMESPACES) or [''])[0]
    properties['date'] = (record.xpath('//dc:date/node()', namespaces=NAMESPACES) or [''])[0]
    properties['pdf_download'] = pdf
    properties['identifiers'] = identifier

    for key, item in properties.iteritems():
        properties[key] = copy_to_unicode(item)

    return properties

def get_ids(record, raw_doc):
    service_id = raw_doc.get('docID')
    url = ''
    all_ids = record.xpath('//dc:identifier/node()', namespaces=NAMESPACES)
    for identifier in all_ids:
        if 'cgi/viewcontent' not in identifier and OAI_DC_BASE[:-7] in identifier:
            url = identifier
    if url == '':
        raise Exception('Warning: No url provided!')

    return {'url': copy_to_unicode(url), 'serviceID': service_id, 'doi': ''}

def get_contributors(record):
    contributors = record.xpath('//dc:creator/node()', namespaces=NAMESPACES)
    contributor_list = []
    for person in contributors:
        name = HumanName(person)
        contributor = {
            'prefix': name.title,
            'given': name.first,
            'middle': name.middle,
            'family': name.last,
            'suffix': name.suffix,
            'email': '',
            'ORCID': '',
            }
        contributor_list.append(contributor)
    return contributor_list

def get_date_created(record):
    date_created = (record.xpath('//dc:date/node()', namespaces=NAMESPACES) or [''])[0]
    date = parse(date_created).isoformat()
    return copy_to_unicode(date)

def get_date_updated(record):
    date_updated = record.xpath('//ns0:header/ns0:datestamp/node()', namespaces=NAMESPACES)[0]
    date = parse(date_updated).isoformat()
    return copy_to_unicode(date)

def get_tags(record):    
    tags = record.xpath('//dc:subject/node()', namespaces=NAMESPACES) or []
    return [copy_to_unicode(tag.lower()) for tag in tags]

def normalize(raw_doc):
    doc = raw_doc.get('doc')
    record = etree.XML(doc)
    
    set_spec = record.xpath('ns0:header/ns0:setSpec/node()', namespaces=NAMESPACES)[0]

    if set_spec.replace('publication:', '') not in series_name_list:
        return None

    # title
    title = record.xpath('//dc:title/node()', namespaces=NAMESPACES)[0]

    # description
    description = (record.xpath('//dc:description/node()', namespaces=NAMESPACES) or [''])[0]

    normalized_dict = {
            'title': copy_to_unicode(title),
            'contributors': get_contributors(record),
            'properties': get_properties(record),
            'description': copy_to_unicode(description),
            'id': get_ids(record, raw_doc),
            'tags': get_tags(record),
            'source': NAME,
            'dateCreated': get_date_created(record),
            'dateUpdated': get_date_updated(record),
    }

    return NormalizedDocument(normalized_dict)
        

if __name__ == '__main__':
    print(lint(consume, normalize))
    