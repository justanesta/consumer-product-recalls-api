This is a document of questions and notes I have reacting to the [api-reference.md](../documentation/api-reference.md) document.

# GET /recalls

## Filter parameters
Why are these recall filter parameters only available for **one** value and not multiple such as via a comma separate list or array-like object? Especially because there is a defined known list of available options

### classification
Distinct values:
```
   classification    
---------------------
- 1
- 2
- 3
- Class I
- Class II
- Class III
- H
- L
- M
- NC
- Public Health Alert
- S
``` 

### lifecycle_status
```
  lifecycle_status   
---------------------
 
- Open
- Closed
- Active Recall
- Public Health Alert
- Completed
- Ongoing
- Closed Recall
- Terminated

```

### distribution_scope
```
 distribution_scope 
--------------------
- Regional
- Nationwide
- Unspecified
- International
```

### distribution_state_codes
```
code 
------
- AK
- AL
- AR
- AS
- AZ
- CA
- CO
- CT
- DC
- DE
- FL
- GA
- GU
- HI
- IA
- ID
- IL
- IN
- KS
- KY
- LA
- MA
- MD
- ME
- MI
- MN
- MO
- MS
- MT
- NC
- ND
- NE
- NH
- NJ
- NM
- NV
- NY
- OH
- OK
- OR
- PA
- PR
- RI
- SC
- SD
- TN
- TX
- UT
- VA
- VI
- VT
- WA
- WI
- WV
- WY

```
### distribution_country_codes

```
 code 
------
 AE
 AF
 AL
 AM
 AO
 AR
 AT
 AU
 AZ
 BA
 BB
 BD
 BE
 BG
 BH
 BN
 BO
 BR
 BS
 BW
 BY
 BZ
 CA
 CH
 CI
 CL
 CM
 CN
 CO
 CR
 CU
 CY
 CZ
 DE
 DK
 DO
 DZ
 EC
 EE
 EG
 ES
 ET
 FI
 FJ
 FR
 GB
 GH
 GR
 GT
 GY
 HK
 HN
 HR
 HT
 HU
 ID
 IE
 IL
 IN
 IQ
 IR
 IS
 IT
 JM
 JO
 JP
 KE
 KH
 KP
 KR
 KW
 KZ
 LA
 LB
 LK
 LT
 LU
 LV
 LY
 MA
 MD
 ME
 MG
 MK
 MM
 MN
 MT
 MU
 MV
 MW
 MX
 MY
 MZ
 NA
 NG
 NI
 NL
 NO
 NP
 NZ
 OM
 PA
 PE
 PG
 PH
 PK
 PL
 PT
 PY
 QA
 RO
 RS
 RU
 RW
 SA
 SD
 SE
 SG
 SI
 SK
 SN
 SO
 SR
 SV
 SY
 TH
 TN
 TR
 TT
 TW
 TZ
 UA
 UG
 UY
 UZ
 VE
 VN
 YE
 ZA
 ZM
 ZW

```

### source_recall_id

These are unique per recall but I'm trying to think of a way to batch lookup a collection of recalls based on a list/array of `source_recall_id`s a user has without looping through individual calls.

## Response Fields
