# Legal Disclaimer

This is founder-drafted guidance, not a legal opinion — it has not been reviewed by a licensed attorney. It reflects a good-faith, non-professional analysis of how the framework relates to the Computer Fraud and Abuse Act (CFAA) and GDPR.

## Computer Fraud and Abuse Act (United States)

The CFAA prohibits unauthorized access to "computer[s] without authorization or exceeding authorized access." XP-Arc, as a piece of software, does not itself violate the CFAA.

Any individual deployment must comply with CFAA terms. Operators are responsible for ensuring their specific use cases are lawful before deployment. Authorized OSINT collection, public data aggregation, and research use cases fall within legal bounds when conducted against systems where the operator has legitimate access rights.

## General Data Protection Regulation (European Union)

GDPR applies to personally identifiable information (PII) collected during scraping. XP-Arc's design includes no PII collection as a core function — it operates on URLs and domain relationships. Any deployment that collects PII as a byproduct must comply with GDPR obligations including lawful basis, data minimization, and subject rights. Data controllers bear full GDPR responsibility for their specific deployments.

## General Principles

- **The framework is a tool.** Tools do not have intent. The operator's intent and the target system's access policies determine legality.
- **Safe harbor by design.** XP-Arc stores no personal data. Entity values are URLs, domains, and relationship metadata. No identity data, financial records, or healthcare records.
- **Jurisdiction variance.** This analysis considers only US and EU law and was not conducted or reviewed by an attorney. Operators in any jurisdiction should obtain independent legal counsel before relying on it.
- **Case-by-case determination.** The legality of any specific deployment requires analysis of target systems, access rights, and local law. When in doubt, obtain independent legal counsel before deployment.

XP-Arc is published as an open research framework. Operators assume full legal responsibility for their specific deployments. The authors make no representation that any specific deployment is lawful in any specific jurisdiction.

## License

XP-Arc is released under the **MIT License**.

- Free to use for any purpose, including commercial production.
- No restrictions on deployment, modification, or commercial use.
- No license fee, no attribution requirement beyond the copyright notice.

See the `LICENSE` file for the full MIT license text.
