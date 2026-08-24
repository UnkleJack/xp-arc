# Legal Disclaimer

XP-Arc has undergone legal review. The framework — as a multi-agent orchestration system — is not itself a violation of the Computer Fraud and Abuse Act (CFAA) or GDPR.

## Computer Fraud and Abuse Act (United States)

The CFAA prohibits unauthorized access to "computer[s] without authorization or exceeding authorized access." XP-Arc, as a piece of software, does not itself violate the CFAA.

Any individual deployment must comply with CFAA terms. Operators are responsible for ensuring their specific use cases are lawful before deployment. Authorized OSINT collection, public data aggregation, and research use cases fall within legal bounds when conducted against systems where the operator has legitimate access rights.

## General Data Protection Regulation (European Union)

GDPR applies to personally identifiable information (PII) collected during scraping. XP-Arc's design includes no PII collection as a core function — it operates on URLs and domain relationships. Any deployment that collects PII as a byproduct must comply with GDPR obligations including lawful basis, data minimization, and subject rights. Data controllers bear full GDPR responsibility for their specific deployments.

## General Principles

- **The framework is a tool.** Tools do not have intent. The operator's intent and the target system's access policies determine legality.
- **Safe harbor by design.** XP-Arc stores no personal data. Entity values are URLs, domains, and relationship metadata. No identity data, financial records, or healthcare records.
- **Jurisdiction variance.** This review covered US and EU law. Operators in other jurisdictions bear responsibility for local requirements.
- **Case-by-case determination.** The legality of any specific deployment requires analysis of target systems, access rights, and local law. When in doubt, obtain independent legal counsel before deployment.

XP-Arc is published as an open research framework. Operators assume full legal responsibility for their specific deployments. The authors make no representation that any specific deployment is lawful in any specific jurisdiction.

## License

XP-Arc is released under the **Apache License, Version 2.0**.

- Free to use for any purpose, including commercial production.
- No restrictions on deployment, modification, or commercial use of the code.
- Includes an express patent grant (§3) and a patent-litigation retaliation clause.
- Reserves trademark rights (§6) separately from the code grant — see the `NOTICE` file for the list of reserved names ("XP-Arc," "DRAGON," "Aboyeur," "Zoran's Law," "SpaZzMatiC") and what "certified"/"official" means in that context.
- No license fee for the code; attribution requirements are limited to preserving copyright, patent, and NOTICE content per §4.

See the `LICENSE` file for the full Apache 2.0 text and the `NOTICE` file for the trademark reservation.
