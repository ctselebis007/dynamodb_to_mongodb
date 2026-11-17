# Sample Queries, Data Volume and Performance Criteria

*Reply to the three questions from the MongoDB team  \|  Version 1.1  \|  Data: EXT\_MongoDB\_Synthetic-DynamoDB-Dataset-v1.0.xlsx*

Right-click and choose Update Field to build the table of contents.

# **1\. Summary**

| You asked for | Short answer |
| :---- | :---- |
| Sample queries and ideal answers | 12 queries over both tables. All of them use the Excel workbook we sent (EXT\_MongoDB\_Synthetic-DynamoDB-Dataset-v1.0.xlsx). Each ideal answer was computed from that workbook, and each query says which sheet and filter reproduce it. |
| Data volume | Today: 15,651 quads in the flat table and 4,974 nested facts in the RDF 1.2 table, under 10 MB. Near term: about 300,000 quads. Horizon: low single-digit millions. |
| Performance | Phase 1 is offline: engineers and AI agents asking questions after the fact, a handful at a time. Seconds are fine; minutes are fine for heavy reports. The must-have is multi-hop traversal in one call. |

# **2\. The workbook and how it maps to DynamoDB**

The data is synthetic: same structure, counts and order as our two DynamoDB tables, with no real records. Each sheet is a flat view of the DynamoDB items.

| Sheet | Rows | In DynamoDB | Use it for |
| :---- | :---- | :---- | :---- |
| talent-rdf-quads | 15,651 | One row \= one item \= one quad. PK \= graph\#subject, SK \= predicate\#object. | T1 to T7 |
| aicp-quads items | 818 | One row \= one item (entity, claim, question, history...). Lists and maps are JSON text; (null) \= NULL. | A5 |
| aicp-quads facts | 4,974 | One row \= one entry of an item's nested facts list (one quad). Predicates are full IRIs. | A1, A2 |
| aicp-quads RDF 1.2 | 239 | One row \= one reifier or claim, with the triple term it is about. | A3, A4 |
| Attribute dictionary | \- | Every attribute with its DynamoDB type and how many items carry it. | Mapping |
| Table definitions | \- | Partition key, sort key and indexes of each table. | Mapping |

Please migrate the items as DynamoDB would hold them: the aicp-quads facts list stays nested inside its item. The facts sheet only makes it readable. Import-ready DynamoDB JSON files are available if you want to load a DynamoDB table first.

# **3\. Sample queries and ideal answers**

"Today" is how many DynamoDB calls the same question needs now. "Ideal" is what we want from MongoDB. "In the workbook" gives the sheet and filter that reproduce the expected answer.

| \# | Question | Pattern | Today (DynamoDB) | Ideal (MongoDB) |
| :---- | :---- | :---- | :---- | :---- |
| T1 | All direct children of one business | Point read | 1 Query | 1 call |
| T2 | All cost centres that belong to one area | Reverse lookup | 1 Query on the predicate GSI; a Scan if the predicate is unknown | 1 call, any predicate |
| T3 | Whole subtree under one business, 3 levels | Multi-hop traversal | 55 Queries, one per node | 1 call (\$graphLookup) |
| T4 | Path from one cost centre up to its business | Upward traversal | 1 Query | 1 call |
| T5 | Lines under one area with their GitHub cost centre | Cross-graph join | 23 Queries | 1 call |
| T6 | Find entities whose label contains a word | Text search | Full Scan of 15,651 items | 1 call, under a second |
| T7 | Cost centres per business, top 5 | Aggregation | Full Scan \+ code | 1 aggregation |
| A1 | Every fact about one entity in the LIVE snapshot | Point read, nested | 1 GetItem | 1 call |
| A2 | Which entities point at one entity | Reverse lookup, nested | Scan of the snapshot \+ code | 1 call |
| A3 | Every reified statement about one subject, with its annotations | RDF 1.2 reifiers | Scan \+ code | 1 call |
| A4 | All claims with who stated, agreed or contested them | RDF 1.2 claims | 1 Query | 1 call |
| A5 | What changed between snapshot v1.02 and LIVE | Version diff | 2 GetItems \+ history Query \+ code | 1 call |

## **T1. Direct children of one business (point read)**

Inputs: graph \= talent:hierarchy, subject \= business:REALGAR\_SHOAL, predicate \= hasArea.

**In the workbook:** sheet talent-rdf-quads; filter graph, subject and predicate as above. Expect 18 rows.

{  
 "subject": "business:REALGAR\_SHOAL",  
 "predicate": "hasArea",  
 "count": 18,  
 "objects": \[  
  "area:REALGAR\_SHOAL\_BARITE\_GLACIER",  
  "area:REALGAR\_SHOAL\_BAUXITE\_COVE",  
  "area:REALGAR\_SHOAL\_CANYON\_BASALT",  
  "area:REALGAR\_SHOAL\_FEN\_CAVERN",  
  "area:REALGAR\_SHOAL\_FLUORITE\_BOG",  
  "… 13 more"  
 \]  
}

## **T2. Cost centres in one area (reverse lookup)**

Inputs: graph \= talent:costcenters, predicate \= belongsToArea, object \= area:WOLFRAMITE\_PRAIRIE. The object is bound and the subject is the unknown.

**In the workbook:** sheet talent-rdf-quads; filter graph, predicate and object as above. Expect 220 rows.

{  
 "object": "area:WOLFRAMITE\_PRAIRIE",  
 "predicate": "belongsToArea",  
 "count": 220,  
 "subjects": \[  
  "costcenter:9900354667",  
  "costcenter:9901457396",  
  "costcenter:9901521554",  
  "costcenter:9901662592",  
  "costcenter:9902111636",  
  "… 215 more"  
 \]  
}

## **T3. Whole subtree under one business (multi-hop, the key query)**

Inputs: start \= business:REALGAR\_SHOAL, follow hasArea, then hasLine, then hasCostCenter, depth up to 3\. Note: the first two hops are in graph talent:hierarchy and the third is in talent:costcenters, so a filter on one graph alone will not reach the cost centres.

**In the workbook:** sheet talent-rdf-quads, three filters in a row. (1) talent:hierarchy, subject \= business:REALGAR\_SHOAL, hasArea: 18 rows. (2) talent:hierarchy, hasLine, subject \= any area from step 1: 36 rows. (3) talent:costcenters, hasCostCenter, subject \= any line from step 2: 148 rows, 143 distinct cost centres.

{  
 "start": "business:REALGAR\_SHOAL",  
 "depth\_1\_areas": 18,  
 "depth\_2\_lines": 36,  
 "depth\_3\_cost\_centre\_links": 148,  
 "depth\_3\_distinct\_cost\_centres": 143,  
 "example\_path": \[  
  "business:REALGAR\_SHOAL",  
  "area:REALGAR\_SHOAL\_PLAIN",  
  "line:REALGAR\_SHOAL\_PLAIN\_TALUS\_HOODOO"  
 \]  
}

Ideal: one server-side call returns all 197 nodes with their depth. Today this takes 55 separate queries, and when an AI agent asks, each hop is a separate tool call.

Some cost centres hang under more than one line (148 links, 143 distinct), so the structure is a graph, not a pure tree. The answer should return each cost centre once.

## **T4. Path from one cost centre up to its business**

Inputs: graph \= talent:costcenters, subject \= costcenter:9900228084.

**In the workbook:** sheet talent-rdf-quads; filter graph and subject, predicate starting with belongsTo. Expect 3 rows. The line label is the rdfs:label row of that line in talent:metadata.

{  
 "costcenter": "costcenter:9900228084",  
 "line": "line:REALGAR\_SHOAL\_ZIRCON\_SAVANNA\_BASIN\_BASALT",  
 "area": "area:REALGAR\_SHOAL\_ZIRCON\_SAVANNA",  
 "business": "business:REALGAR\_SHOAL",  
 "line\_label": "TALUS-Basin Magnetite & Hoodoo"  
}

## **T5. Lines under one area with their GitHub cost centre (cross-graph)**

Inputs: area \= area:BUTTE\_MORAINE\_ESKER. Lines come from talent:hierarchy; the GitHub mapping comes from talent:github.

**In the workbook:** sheet talent-rdf-quads. (1) talent:hierarchy, subject \= area:BUTTE\_MORAINE\_ESKER, hasLine: 22 rows. (2) talent:github, hasGitHubCostCenter, subject \= any line from step 1: 22 rows.

{  
 "area": "area:BUTTE\_MORAINE\_ESKER",  
 "lines": 22,  
 "lines\_with\_github\_cost\_centre": 22,  
 "rows": \[  
  {  
   "line": "line:BUTTE\_MORAINE\_ESKER\_WOLFRAMITE\_702",  
   "github": "ghcostcenter:GH\_QUARTZ\_VARISCITE"  
  },  
  {  
   "line": "line:BUTTE\_MORAINE\_ESKER\_BUTTE\_GRANITE",  
   "github": "ghcostcenter:GH\_QUARTZ\_VARISCITE"  
  },  
  {  
   "line": "line:BUTTE\_MORAINE\_ESKER\_REALGAR\_TOMBOLO",  
   "github": "ghcostcenter:GH\_QUARTZ\_VARISCITE"  
  },  
  {  
   "line": "line:BUTTE\_MORAINE\_ESKER\_SODALITE\_CAVERN",  
   "github": "ghcostcenter:GH\_QUARTZ\_VARISCITE"  
  }  
 \]  
}

## **T6. Text search on labels**

Inputs: word \= "LAGOON", match anywhere in subject\_label or object\_label, all graphs.

**In the workbook:** sheet talent-rdf-quads; text filter "contains LAGOON" on subject\_label, then on object\_label. Together they name 14 distinct entities.

{  
 "word": "LAGOON",  
 "distinct\_entities": 14,  
 "by\_type": {  
  "area": 4,  
  "line": 10  
 },  
 "examples": \[  
  "area:GRANITE\_MALACHITE\_LAGOON",  
  "area:GYPSUM\_LAGOON",  
  "area:REALGAR\_SHOAL\_ORPIMENT\_LAGOON",  
  "area:SODALITE\_ESKER\_BAUXITE\_LAGOON",  
  "… 10 more"  
 \]  
}

## **T7. Cost centres per business (aggregation)**

**In the workbook:** sheet talent-rdf-quads; filter talent:costcenters and belongsToBusiness, then a pivot counting rows per object. 20 businesses.

{  
 "top\_5": \[  
  {  
   "business": "business:WOLFRAMITE",  
   "cost\_centres": 1198  
  },  
  {  
   "business": "business:REALGAR\_SHOAL",  
   "cost\_centres": 143  
  },  
  {  
   "business": "business:BUTTE\_MORAINE",  
   "cost\_centres": 136  
  },  
  {  
   "business": "business:GRANITE",  
   "cost\_centres": 70  
  },  
  {  
   "business": "business:WADI",  
   "cost\_centres": 66  
  }  
 \],  
 "businesses\_total": 20  
}

## **A1. Every fact about one entity (nested, LIVE snapshot)**

Inputs: pk \= QUADS\#LIVE, entity id \= S-sso\_claude\_ai\_enforced. Facts are inside the entity item, in a nested list.

**In the workbook:** sheet aicp-quads facts; filter pk \= QUADS\#LIVE and entity id. Expect 21 rows.

{  
 "entity": "S-sso\_claude\_ai\_enforced",  
 "facts": 21,  
 "by\_predicate": {  
  "type": \[  
   "https\://example.org/mobilesec/ontology/LLMVendorControl"  
  \],  
  "label": \[  
   "Synthetic item 165: step gateway policy"  
  \],  
  "apiField": \[  
   "sso\_claude\_ai\_enforced"  
  \],  
  "confidence": \[  
   "https\://example.org/mobilesec/ontology/High"  
  \],  
  "enforcedBy": \[  
   "ClaudeAdminConsole"  
  \],  
  "evidence": \[  
   "Source document E \- section 9: synthetic excerpt baseline group verify audit document team test domain",  
   "Source document F \- section 7: synthetic excerpt LLMGeneric finding verify result route",  
   "Source document H \- section 5: synthetic excerpt record evidence header"  
  \],  
  "granularity": \[  
   "https\://example.org/mobilesec/ontology/OrgWide"  
  \],  
  "inOrganization": \[  
   "Org-ExampleProduction"  
  \],  
  "measuredOn": \[  
   "2026-06-19",  
   "2026-04-27"  
  \],  
  "measuredValue": \[  
   "true"  
  \],  
  "status": \[  
   "https\://example.org/mobilesec/ontology/InPlace"  
  \],  
  "vendorSpecific": \[  
   "https\://example.org/mobilesec/ontology/ClaudeSpecific"  
  \],  
  "comment": \[  
   "Synthetic note 031: session share account profile plan OverAllowing IntuneMDM config ticket domain issue audit test status server check check Resource."  
  \],  
  "conflictsWith": \[  
   "claim-person05-sso-blocks-google"  
  \],  
  "coversAccountType": \[  
   "https\://example.org/mobilesec/ontology/ExampleAuthenticated"  
  \],  
  "doesNotCoverAccountType": \[  
   "https\://example.org/mobilesec/ontology/PersonalNonExampleDomain"  
  \],  
  "scope": \[  
   "https\://example.org/mobilesec/ontology/Generic"  
  \],  
  "inventoryTool": \[  
   "33"  
  \]  
 }  
}

## **A2. Which entities point at one entity (reverse, nested)**

Inputs: pk \= QUADS\#LIVE, object id \= ClaudeAdminConsole. Entity references inside facts use the bare id (for example "ClaudeAdminConsole"), while each entity also carries a full iri attribute.

**In the workbook:** sheet aicp-quads facts; filter pk \= QUADS\#LIVE and object.id \= ClaudeAdminConsole. Expect 24 rows.

{  
 "object": "ClaudeAdminConsole",  
 "facts\_pointing\_here": 24,  
 "distinct\_subjects": 24,  
 "by\_predicate": {  
  "enforcedBy": 24  
 },  
 "examples": \[  
  {  
   "subject": "K01",  
   "predicate": "enforcedBy"  
  },  
  {  
   "subject": "K06",  
   "predicate": "enforcedBy"  
  },  
  {  
   "subject": "S-allowed\_invite\_domains",  
   "predicate": "enforcedBy"  
  },  
  {  
   "subject": "S-claude\_code\_trusted\_devices",  
   "predicate": "enforcedBy"  
  }  
 \]  
}

## **A3. Reified statements about one subject (RDF 1.2)**

Inputs: pk \= QUADS\#LIVE, triple subject \= K06. A reifier is an entity whose reifies map holds a triple term; its own facts annotate that statement (confidence, evidence).

**In the workbook:** sheet aicp-quads RDF 1.2; filter pk \= QUADS\#LIVE and triple.subject \= K06. Expect 5 rows. Each reifier's confidence is in sheet aicp-quads facts (entity id \= the reifier, predicate ending in /confidence).

{  
 "subject": "K06",  
 "reifiers": 5,  
 "rows": \[  
  {  
   "reifier": "assess-q01-person05-sso-claim",  
   "graph": "inferred",  
   "triple": \[  
    "K06",  
    "blocks",  
    "GoogleSignIn"  
   \],  
   "confidence": "High",  
   "evidence": 6  
  },  
  {  
   "reifier": "claim-person05-sso-blocks-google",  
   "graph": "meeting-20260702",  
   "triple": \[  
    "K06",  
    "blocks",  
    "GoogleSignIn"  
   \],  
   "confidence": null,  
   "evidence": 1  
  },  
  {  
   "reifier": "rf-5c0362397f57",  
   "graph": "inferred",  
   "triple": \[  
    "K06",  
    "granularity",  
    "OrgWide"  
   \],  
   "confidence": "High",  
   "evidence": 0  
  },  
  {  
   "reifier": "rf-2eebe635da79",  
   "graph": "inferred",  
   "triple": \[  
    "K06",  
    "identifiedAs",  
    "V-RequireSSOForClaude"  
   \],  
   "confidence": "High",  
   "evidence": 0  
  }  
 \]  
}

## **A4. Claims and their stance lists (RDF 1.2)**

**In the workbook:** sheet aicp-quads RDF 1.2; filter sk starting with CLAIM\#. Expect 7 rows, with statedBy, agreedBy, contestedBy and resolutionState columns.

{  
 "claims": 7,  
 "rows": \[  
  {  
   "id": "assess-q01-person05-sso-claim",  
   "pk": "QUADS\#v1.02",  
   "triple": \[  
    "K06",  
    "blocks",  
    "GoogleSignIn"  
   \],  
   "statedBy": \[\],  
   "agreedBy": \[\],  
   "contestedBy": \[\],  
   "resolutionState": "ResolvedPartlySupported"  
  },  
  {  
   "id": "claim-person08-android-chrome",  
   "pk": "QUADS\#v1.02",  
   "triple": \[  
    "ClaudeAI-AndroidWorkProfileChrome",  
    "allowsCorporateDataUpload",  
    "true"  
   \],  
   "statedBy": \[  
    "Person-08"  
   \],  
   "agreedBy": \[\],  
   "contestedBy": \[\],  
   "resolutionState": "Unresolved"  
  },  
  {  
   "id": "claim-person08-mobile-web-upload",  
   "pk": "QUADS\#v1.02",  
   "triple": \[  
    "ClaudeAI-MobileBrowser",  
    "allowsCorporateDataUpload",  
    "true"  
   \],  
   "statedBy": \[  
    "Person-08"  
   \],  
   "agreedBy": \[\],  
   "contestedBy": \[  
    "Person-02"  
   \],  
   "resolutionState": "Unresolved"  
  }  
 \]  
}

## **A5. What changed between snapshot v1.02 and LIVE**

Inputs: compare pk \= QUADS\#v1.02 with pk \= QUADS\#LIVE for the same sk, plus the HIST records.

**In the workbook:** sheet aicp-quads items. Filter pk \= QUADS\#LIVE with itemVersion above 0: 2 entities. Filter sk starting with HIST\#ENTITY\#: 4 history rows; the changes column holds before and after.

{  
 "changed\_entities": 2,  
 "rows": \[  
  {  
   "entity": "A4",  
   "itemVersion": "2",  
   "liveRevision": "4",  
   "facts\_v1.02": 10,  
   "facts\_LIVE": 10,  
   "changes": \[  
    {  
     "history": "00000003",  
     "field": "inventoryTools",  
     "op": "set",  
     "before": \[\],  
     "after": \[  
      "33"  
     \]  
    },  
    {  
     "history": "00000004",  
     "field": "inventoryTools",  
     "op": "set",  
     "before": \[  
      "33"  
     \],  
     "after": \[\]  
    }  
   \]  
  },  
  {  
   "entity": "S-ip\_allowlist",  
   "itemVersion": "2",  
   "liveRevision": "2",  
   "facts\_v1.02": 19,  
   "facts\_LIVE": 19,  
   "changes": \[  
    {  
     "history": "00000001",  
     "field": "confidence",  
     "op": "replace",  
     "before": "High",  
     "after": "Medium"  
    },  
    {  
     "history": "00000002",  
     "field": "confidence",  
     "op": "replace",  
     "before": "Medium",  
     "after": "High"  
    }  
   \]  
  }  
 \]  
}

# **4\. Data volume: current and future**

## **Current (measured, November 2026\)**

| Store | Items | Quads / facts | Named graphs | Entities | Size |
| :---- | :---- | :---- | :---- | :---- | :---- |
| Flat quad table (talent-rdf-quads) | 15,651 | 15,651 | 4 | 2,363 (costcenter 1,826, line 372, area 138, business 21, ghcostcenter 6\) | 5.8 MB |
| RDF 1.2 table (aicp-quads) | 818 | 4,974 (2 snapshots of 2,487) | 14 | 265 per snapshot, 116 reifiers, 7 claims | 1.5 MB |
| Two more quad stores, not in the first test | 3,789 | about 487,500 | 45 | \- | about 122 MB  **\[CONFIRM: include or remove\]** |

Largest single item today: about 27 KB (the vocabulary item). Typical item: well under 4 KB.

## **Future (estimates, not measurements)**

| Horizon | Quads | What drives it |
| :---- | :---- | :---- |
| Near term | about 300,000 | New sources: directory security groups (\~50,000), source-control teams and repos (\~25,000), cost-centre budgets (\~5,000), application inventory (\~200,000) |
| Horizon | low single-digit millions | Many more enterprise sources, some not yet identified. The model must take a new source with an extractor only, no schema change. |
| Snapshots | \+ about 2,500 per load | Each RDF 1.2 load adds a full snapshot. **\[CONFIRM: how many snapshots to keep\]** |

## **Write pattern**

| Write | Shape | How often |
| :---- | :---- | :---- |
| Full graph refresh | Bulk replace of one named graph, about 15,000 documents today | Nightly or on demand |
| Change event | Delete one quad, insert its replacement, ideally atomic | Ad hoc, more often later |
| Narrative update | A few fields on entity documents | Occasional, in batches |
| Read / write mix | About 95% reads, 5% writes | \- |

# **5\. Performance criteria**

## **Phase 1: size for this**

Phase 1 is offline. No user-facing request waits on this store. We will measure and record the numbers rather than treat them as pass/fail.

| Area | Requirement |
| :---- | :---- |
| Point read and reverse lookup (T1, T2, T4, A1, A2) | Fast enough not to be noticed inside an agent turn. Working target: under 1 second at p95. **\[CONFIRM\]** |
| Multi-hop traversal (T3) | One server-side call, depth 3 to 5, same result set as the per-hop method. Working target: under 2 seconds at p95. **\[CONFIRM\]** |
| Text search (T6) | Under a second is fine. |
| Aggregations and reconciliation (T7, A5) | Seconds are fine; minutes are acceptable for heavy reports. |
| Full graph reload | Minutes. Working target: 15,000 documents in under 5 minutes. **\[CONFIRM\]** |
| Concurrency | A handful of readers at once: the platform team and the AI agents they run. |
| Consistency | Eventual consistency and secondary reads are fine. No read-your-own-write need. |
| Freshness | Org hierarchy: 7 days (refreshed nightly). Ownership, policy and identity: 24 hours. |
| Sync lag while both stores run | Working target 60 seconds; can be relaxed if it drives cost. |
| Availability | Not critical. A one-hour outage slows troubleshooting; no AI request fails. |
| Backup | Point-in-time recovery preferred, because a bad bulk load is a realistic failure. |
| Security | US region (us-east-1), TLS 1.2 or higher, encryption at rest, private connectivity, credentials in a secrets store or IAM authentication, auditable access. |

## **Later phase: design awareness only, do not size for it**

| Future use | Eventual budget |
| :---- | :---- |
| Policy check on every AI request | under 100 ms |
| Request metadata enrichment | under 200 ms |
| Persona lookup at login | under 500 ms |
| Concurrency | low hundreds of readers |

Please tell us if any Phase 1 choice would block these later budgets.

# **6\. Points we would like your view on**

* T3 crosses two named graphs. What is the right \$graphLookup set-up when one hop changes graph?  
* Entity references inside facts use bare ids, while entities also carry a full iri. Should we normalise one way before loading?  
* The RDF 1.2 table keeps whole snapshots (v1.02, LIVE) plus a pointer. One collection with a version field, or one per snapshot?  
* Reifiers and claims hold triple terms (a statement used as a value). How should they be indexed for A3?