<a id="readme-top"></a>

<!-- PROJECT SHIELDS -->
[![Register][register-shield]][register-url]
[![Contact][contact-shield]][contact-url]

<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://www.empirasign.com">
    <img src="https://www.empirasign.com/site_media/img/Empirasign_Logo_White.svg" alt="Logo" width="150" height="80">
  </a>

  <h3 align="center">Python API Access</h3>

  <p align="center">
    Access all available Empirasign Market Data & Parser API REST endpoints with Python. Example scripts illustrating the most common use-cases are included in this repository.
    <br /><br>
    <a href="https://www.empirasign.com/v1/market-api-docs/"><strong>Explore the Market Data API docs »</strong></a>
    <br />
    <a href="https://www.empirasign.com/v1/parser-api-docs/"><strong>Explore the Parser API docs »</strong></a>
    <br /><br>
    <a href="https://www.empirasign.com/register/">Register for a Trial</a>
    &middot;
    <a href="mailto:info@empirasign.com">Contact Us</a>
    &middot;
    <a href="https://www.empirasign.com/developer-resources">Developer Resources</a>
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-api">About The API</a>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li>
        <a href="#endpoints">Endpoints</a>
        <ul>
            <li><a href="#market-endpoints">Market Data API</a></li>
            <li><a href="#parser-endpoints">Parser API</a></li>
        </ul>
    </li>
    <li><a href="#use-cases">Use Cases</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
  </ol>
</details>

<!-- ABOUT THE PROJECT -->
## About The API
Empirasign is the leading provider of secondary market trading data for the Structured Products markets. Our real-time database offers the most exhaustive data set of secondary market activity for all ABS, MBS, & CMBS, with BWIC history dating as far back as 2010. We also cover Corporate Bonds and Levered Loans.

Empirasign offers two APIs which enable the most comprehensive real-time look into the secondary markets available anywhere.

#### The Market Data API
*Access real-time market observations from our consortium of market participants for an overview of the entire secondary market*
* Fixed Income & Structured Products
  * BWIC color & dealer price talk
  * Dealer bids, offers, and 2-way markets
* Corporate IG/HY quotes <mark>New</mark>

#### The Parser API (Parser as a Service)
*Convert your own Inbox emails into parsed, cleaned, & validated data*
* BWIC emails
* Dealer Runs emails
* Corporate IG/HY emails <mark>New</mark>
* Loans emails <mark>New</mark>
* CDS emails <mark>New</mark>

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- GETTING STARTED -->
## Getting Started

Follow these steps to install the Empirasign python SDK and set up your project locally.


### Installation

1. Obtain API credentials by signing up at our [Free Trial Registration Page](https://www.empirasign.com/register) or reaching out to info@empirasign.com
2. Install package through the github repository
   ```sh
   pip install git+https://github.com/empirasign/python-sdk.git
   ```
<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- USAGE EXAMPLES -->
## Usage

Authentication is simple, just instantiate your Empirasign client using your provided key and secret.

#### Market Data API
```py
from empirasign import MarketDataClient

api = MarketDataClient("Empirasign_Key", "Empirasign_Secret")
```

#### Parser API
```py
from empirasign import ParserClient

api = ParserClient("Empirasign_Key", "Empirasign_Secret")
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- ROADMAP -->
## Market Data Endpoints

Host: https://www.empirasign.com/api/v1

| HTTP METHOD   | API ENDPOINT     | QUOTA HIT                      | CLASS METHOD
| :---          | :---             | :---                           | :---
| POST          |  /bonds/         | **1 per requested bond**           |  `get_market_data`
| GET           |  /bwics/         | None                           |  `get_bwics`
| POST          |  /nport/         | **1 per requested bond**           |  `get_nport`
| GET           |  /offers/        | None                           |  `get_available_runs`
| GET           |  /offers/        | **1 per offer**                    |  `get_dealer_runs`
| GET           |  /deal-classes/  | None                           |  `get_deal`
| GET           |  /all-bonds/     | None                           |  `get_active_bonds`
| POST          |  /collab/        | None                           |  `get_suggested`
| GET           |  /mbsfeed/       | None                           |  `get_events`
| GET           |  /query-log/     | None                           |  `get_query_log`
| GET           |  /mystatus/      | None                           |  `get_status`
| POST          |  /corp-bonds/    | **1 per requested bond, per page** | `get_corp_market_data`
| GET           |  /corp-runs/     | None                           | `get_corp_available_runs`
| GET           |  /corp-runs/     | **1 per offer, per page**          | `get_corp_dealer_runs`

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Parser Endpoints

Host: https://api.empirasign.com/v1

| HTTP METHOD   | API ENDPOINT     | QUOTA HIT                   | CLASS METHOD
| :---          | :---             | :---                        | :---
| POST | /parse-run/<br>/parse-bwic/<br>/parse-corp/<br>/parse-loan/<br>/parse-cds/ | **1 per request** | `parse_email_file`<br>`parse_eml`<br>`parse_msg`
| POST          | /id-mapper/      | **1 per id**                | `get_id_mapping`
| POST          | /mydata/         | None                        | `get_mydata`
| POST          | /raw-msg/{tx_id}/| None                        | `get_raw_msg`
| POST          | /submit-email/   | None                        | `submit_eml`<br>`submit_msg`

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- USE CASES -->
## Common Use Cases (Example Scripts)

Example scripts for common client API use-cases are included in /examples. All example database implementations use SQLite for demonstration purposes.

### Market Data API
Directory: `/examples/market`
| Example Script     | Use Case
| :---             | :---
| `bwic_poll.py`     | Intraday polling for market data for bonds that appear on BWICs
| `runs_poll.py` | Intraday polling for bid, offer, and 2-way market observations that appear on Dealer Runs
| `corp_poll.py` | Intraday polling for Corporate IG/HY quotes
| `intex_mktd.py` | Export Empirasign market data to INTEXCalc .mktd format
| `bwics_to_intex.py` | Export Empirasign BWIC data to INTEXCalc .bwic format
| `eod_data_grab.py` | End-of-day pull of all available market observations

### Parser API
Directory: `/examples/parser`
| Example Script            | Use Case
| :---                      | :---
| `parse_bwic.py`           | Parse a BWIC embedded email
| `parse_run.py`            | Parse a dealer runs embedded email
| `parse_imap_inbox.py`     | Monitor IMAP Inbox for live dealer runs parsing
| `parse_outlook_inbox.py`  | Monitor Outlook client Inbox for live dealer runs parsing
| `parse_msgraph_inbox.py`  | Monitor Outlook Inbox via Microsoft Graph API for live dealer runs parsing
| `call_mapper.py`          | Map common identifiers to bonds
| `mydata_poll.py`          | Export MyData


<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- LICENSE -->
## License

Distributed under the MIT License. See `LICENSE.txt` for more information.

<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- CONTACT -->
## Contact

Empirasign Strategies LLC - [@empirasign](https://twitter.com/empirasign) - info@empirasign.com

Project Link: [https://github.com/empirasign/python-sdk](https://github.com/empirasign/python-sdk)

<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- MARKDOWN LINKS & IMAGES -->
[register-shield]: https://img.shields.io/badge/-Register%20For%20A%20Free%20Trial-blue.svg?style=for-the-badge
[register-url]: https://www.empirasign.com/register
[contact-shield]: https://img.shields.io/badge/-Contact%20Us-gray.svg?style=for-the-badge
[contact-url]: https://www.empirasign.com/contactus