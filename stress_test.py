#!/usr/bin/env python3
"""
XP-Arc Stress Test — 5000 Entity Gauntlet.

Generates 5000 diverse seed entities (URLs + domains),
injects them into the pool, and runs the full brigade
to test throughput, Aboyeur validation, Zoran's Law
stability under load, and SpaZzMatiC monitoring.
"""

import os
import sys
import json
import time
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xp_arc.core.pool import IntelligencePool
from xp_arc.core.executive import ExecutiveChef
from xp_arc.stations.forager import TheForager
from xp_arc.stations.analyst import TheAnalyst
from xp_arc.stations.sentinel import TheSentinel
from xp_arc.stations.plongeur import ThePlongeur
from xp_arc.monitoring.zorans_law import ZoransLaw
from xp_arc.monitoring.spazzmatic import SpaZzMatiC


# ─── Seed URL Generation ───
# Real, diverse URLs across multiple categories

SEED_URLS = [
    # News & Media
    "https://news.ycombinator.com",
    "https://lobste.rs",
    "https://arstechnica.com",
    "https://www.wired.com",
    "https://www.theverge.com",
    "https://techcrunch.com",
    "https://www.reuters.com",
    "https://apnews.com",
    "https://www.bbc.com/news",
    "https://www.aljazeera.com",
    "https://www.npr.org",
    "https://www.pbs.org",
    "https://www.economist.com",
    "https://www.ft.com",
    "https://www.bloomberg.com",
    "https://slashdot.org",
    "https://www.engadget.com",
    "https://www.cnet.com",
    "https://mashable.com",
    "https://gizmodo.com",
    # Tech & Dev
    "https://github.com",
    "https://gitlab.com",
    "https://stackoverflow.com",
    "https://dev.to",
    "https://hackernews.com",
    "https://www.reddit.com/r/programming",
    "https://www.reddit.com/r/python",
    "https://www.reddit.com/r/machinelearning",
    "https://www.producthunt.com",
    "https://httpbin.org/html",
    "https://docs.python.org/3/",
    "https://developer.mozilla.org",
    "https://www.w3.org",
    "https://nodejs.org",
    "https://www.rust-lang.org",
    "https://go.dev",
    "https://www.typescriptlang.org",
    "https://vuejs.org",
    "https://react.dev",
    "https://angular.dev",
    # AI & ML
    "https://openai.com",
    "https://www.anthropic.com",
    "https://ai.google",
    "https://huggingface.co",
    "https://arxiv.org",
    "https://paperswithcode.com",
    "https://www.deepmind.com",
    "https://stability.ai",
    "https://mistral.ai",
    "https://cohere.com",
    # Education & Reference
    "https://en.wikipedia.org/wiki/Kitchen_brigade_system",
    "https://en.wikipedia.org/wiki/Multi-agent_system",
    "https://en.wikipedia.org/wiki/OSINT",
    "https://en.wikipedia.org/wiki/SQLite",
    "https://en.wikipedia.org/wiki/Escoffier",
    "https://www.khanacademy.org",
    "https://www.coursera.org",
    "https://www.edx.org",
    "https://ocw.mit.edu",
    "https://www.freecodecamp.org",
    # Government & Standards
    "https://www.usa.gov",
    "https://data.gov",
    "https://www.nist.gov",
    "https://www.ietf.org",
    "https://www.iso.org",
    # Cloud & Infra
    "https://aws.amazon.com",
    "https://cloud.google.com",
    "https://azure.microsoft.com",
    "https://www.digitalocean.com",
    "https://www.cloudflare.com",
    "https://vercel.com",
    "https://www.heroku.com",
    "https://fly.io",
    "https://railway.app",
    "https://render.com",
]

# ─── Domain Generation ───
# Diverse, real-world domains across categories

DOMAIN_POOLS = {
    'tech_companies': [
        'apple.com', 'microsoft.com', 'google.com', 'amazon.com', 'meta.com',
        'nvidia.com', 'intel.com', 'amd.com', 'ibm.com', 'oracle.com',
        'salesforce.com', 'adobe.com', 'vmware.com', 'cisco.com', 'dell.com',
        'hp.com', 'samsung.com', 'sony.com', 'lg.com', 'panasonic.com',
        'qualcomm.com', 'broadcom.com', 'tsmc.com', 'asml.com', 'arm.com',
        'palantir.com', 'snowflake.com', 'databricks.com', 'confluent.io', 'elastic.co',
        'twilio.com', 'stripe.com', 'square.com', 'shopify.com', 'atlassian.com',
        'slack.com', 'zoom.us', 'dropbox.com', 'box.com', 'docusign.com',
        'servicenow.com', 'workday.com', 'splunk.com', 'paloaltonetworks.com', 'crowdstrike.com',
        'fortinet.com', 'zscaler.com', 'okta.com', 'cloudflare.com', 'fastly.com',
    ],
    'ai_companies': [
        'openai.com', 'anthropic.com', 'deepmind.com', 'cohere.com', 'mistral.ai',
        'stability.ai', 'midjourney.com', 'runway.ml', 'jasper.ai', 'copy.ai',
        'huggingface.co', 'replicate.com', 'modal.com', 'anyscale.com', 'ray.io',
        'wandb.ai', 'neptune.ai', 'mlflow.org', 'dvc.org', 'labelbox.com',
        'scale.com', 'snorkel.ai', 'datarobot.com', 'h2o.ai', 'c3.ai',
        'perplexity.ai', 'together.ai', 'fireworks.ai', 'groq.com', 'cerebras.ai',
        'inflection.ai', 'adept.ai', 'character.ai', 'pi.ai', 'writesonic.com',
        'synthesia.io', 'descript.com', 'otter.ai', 'assembly.ai', 'whisper.ai',
    ],
    'dev_tools': [
        'github.com', 'gitlab.com', 'bitbucket.org', 'jetbrains.com', 'vscode.dev',
        'replit.com', 'codepen.io', 'jsfiddle.net', 'codesandbox.io', 'stackblitz.com',
        'vercel.com', 'netlify.com', 'heroku.com', 'render.com', 'railway.app',
        'fly.io', 'deno.land', 'bun.sh', 'npmjs.com', 'pypi.org',
        'crates.io', 'rubygems.org', 'packagist.org', 'nuget.org', 'maven.apache.org',
        'docker.com', 'kubernetes.io', 'terraform.io', 'ansible.com', 'puppet.com',
        'jenkins.io', 'circleci.com', 'travis-ci.com', 'github.io', 'readthedocs.io',
        'swagger.io', 'postman.com', 'insomnia.rest', 'httpie.io', 'curl.se',
    ],
    'news_media': [
        'nytimes.com', 'washingtonpost.com', 'wsj.com', 'reuters.com', 'apnews.com',
        'bbc.com', 'cnn.com', 'foxnews.com', 'nbcnews.com', 'abcnews.go.com',
        'theguardian.com', 'independent.co.uk', 'telegraph.co.uk', 'ft.com', 'economist.com',
        'bloomberg.com', 'cnbc.com', 'marketwatch.com', 'yahoo.com', 'msn.com',
        'vice.com', 'vox.com', 'buzzfeed.com', 'huffpost.com', 'dailymail.co.uk',
        'politico.com', 'axios.com', 'thehill.com', 'salon.com', 'slate.com',
        'wired.com', 'arstechnica.com', 'theverge.com', 'engadget.com', 'gizmodo.com',
        'techcrunch.com', 'zdnet.com', 'cnet.com', 'pcmag.com', 'tomsguide.com',
    ],
    'education': [
        'mit.edu', 'stanford.edu', 'harvard.edu', 'berkeley.edu', 'caltech.edu',
        'princeton.edu', 'yale.edu', 'columbia.edu', 'uchicago.edu', 'upenn.edu',
        'cornell.edu', 'cmu.edu', 'gatech.edu', 'umich.edu', 'utexas.edu',
        'uw.edu', 'ucla.edu', 'nyu.edu', 'usc.edu', 'duke.edu',
        'ox.ac.uk', 'cam.ac.uk', 'ethz.ch', 'epfl.ch', 'tum.de',
        'khanacademy.org', 'coursera.org', 'edx.org', 'udacity.com', 'udemy.com',
        'codecademy.com', 'freecodecamp.org', 'brilliant.org', 'duolingo.com', 'skillshare.com',
        'pluralsight.com', 'linkedin.com', 'masterclass.com', 'skillsoft.com', 'oreilly.com',
    ],
    'government': [
        'usa.gov', 'whitehouse.gov', 'congress.gov', 'senate.gov', 'house.gov',
        'cia.gov', 'fbi.gov', 'nsa.gov', 'dhs.gov', 'state.gov',
        'treasury.gov', 'defense.gov', 'justice.gov', 'epa.gov', 'nasa.gov',
        'nih.gov', 'cdc.gov', 'fda.gov', 'sec.gov', 'ftc.gov',
        'nist.gov', 'data.gov', 'census.gov', 'bls.gov', 'usgs.gov',
        'noaa.gov', 'energy.gov', 'ed.gov', 'hud.gov', 'dot.gov',
        'gov.uk', 'europa.eu', 'un.org', 'who.int', 'worldbank.org',
        'imf.org', 'wto.org', 'nato.int', 'oecd.org', 'iaea.org',
    ],
    'social_platforms': [
        'twitter.com', 'facebook.com', 'instagram.com', 'tiktok.com', 'snapchat.com',
        'pinterest.com', 'tumblr.com', 'reddit.com', 'quora.com', 'medium.com',
        'substack.com', 'wordpress.com', 'blogger.com', 'ghost.org', 'wix.com',
        'squarespace.com', 'weebly.com', 'discord.com', 'telegram.org', 'signal.org',
        'whatsapp.com', 'line.me', 'wechat.com', 'viber.com', 'skype.com',
        'twitch.tv', 'youtube.com', 'vimeo.com', 'dailymotion.com', 'rumble.com',
        'spotify.com', 'soundcloud.com', 'bandcamp.com', 'apple.com', 'deezer.com',
        'goodreads.com', 'imdb.com', 'rottentomatoes.com', 'letterboxd.com', 'myanimelist.net',
    ],
    'security_infosec': [
        'cve.org', 'nvd.nist.gov', 'exploit-db.com', 'shodan.io', 'censys.io',
        'virustotal.com', 'malwarebytes.com', 'kaspersky.com', 'norton.com', 'avast.com',
        'krebsonsecurity.com', 'darkreading.com', 'threatpost.com', 'bleepingcomputer.com', 'hackernews.com',
        'owasp.org', 'sans.org', 'mitre.org', 'cisa.gov', 'cert.org',
        'bugcrowd.com', 'hackerone.com', 'synack.com', 'intigriti.com', 'cobalt.io',
        'snyk.io', 'sonarqube.org', 'checkmarx.com', 'veracode.com', 'qualys.com',
        'rapid7.com', 'tenable.com', 'nessus.org', 'metasploit.com', 'burpsuite.net',
        'wireshark.org', 'nmap.org', 'kali.org', 'parrotsec.org', 'tails.boum.org',
    ],
    'finance': [
        'jpmorgan.com', 'goldmansachs.com', 'morganstanley.com', 'bankofamerica.com', 'citigroup.com',
        'wellsfargo.com', 'hsbc.com', 'barclays.com', 'ubs.com', 'creditsuisse.com',
        'blackrock.com', 'vanguard.com', 'fidelity.com', 'schwab.com', 'etrade.com',
        'robinhood.com', 'coinbase.com', 'binance.com', 'kraken.com', 'gemini.com',
        'blockchain.com', 'chainalysis.com', 'consensys.net', 'ethereum.org', 'bitcoin.org',
        'solana.com', 'cardano.org', 'polkadot.network', 'avalabs.org', 'near.org',
        'visa.com', 'mastercard.com', 'paypal.com', 'venmo.com', 'cashapp.com',
        'plaid.com', 'marqeta.com', 'affirm.com', 'klarna.com', 'afterpay.com',
    ],
    'gaming': [
        'steampowered.com', 'epicgames.com', 'gog.com', 'ea.com', 'ubisoft.com',
        'blizzard.com', 'riotgames.com', 'bethesda.net', 'rockstargames.com', 'valvesoftware.com',
        'nintendo.com', 'playstation.com', 'xbox.com', 'unity.com', 'unrealengine.com',
        'godotengine.org', 'itch.io', 'gamejolt.com', 'indiedb.com', 'moddb.com',
        'twitch.tv', 'discord.com', 'teamspeak.com', 'mumble.info', 'guilded.gg',
        'roblox.com', 'minecraft.net', 'fortnite.com', 'leagueoflegends.com', 'dota2.com',
        'igdb.com', 'howlongtobeat.com', 'pcgamingwiki.com', 'speedrun.com', 'retroachievements.org',
        'nexusmods.com', 'curseforge.com', 'modrinth.com', 'thunderstore.io', 'gamebanana.com',
    ],
    'science_research': [
        'nature.com', 'science.org', 'cell.com', 'thelancet.com', 'nejm.org',
        'plos.org', 'biorxiv.org', 'medrxiv.org', 'chemrxiv.org', 'ssrn.com',
        'scholar.google.com', 'semanticscholar.org', 'researchgate.net', 'academia.edu', 'orcid.org',
        'doi.org', 'crossref.org', 'pubmed.ncbi.nlm.nih.gov', 'europepmc.org', 'sciencedirect.com',
        'springer.com', 'wiley.com', 'elsevier.com', 'taylorfrancis.com', 'sagepub.com',
        'ieee.org', 'acm.org', 'ams.org', 'aps.org', 'rsc.org',
        'cern.ch', 'fermilab.gov', 'ligo.caltech.edu', 'jpl.nasa.gov', 'esa.int',
        'spacex.com', 'blueorigin.com', 'rocketlabusa.com', 'relativityspace.com', 'astranis.com',
    ],
    'international_tlds': [
        'rakuten.co.jp', 'alibaba.com', 'tencent.com', 'baidu.com', 'jd.com',
        'samsung.co.kr', 'naver.com', 'kakao.com', 'line.co.jp', 'softbank.jp',
        'siemens.de', 'sap.com', 'bosch.com', 'daimler.com', 'bmw.de',
        'philips.com', 'shell.com', 'unilever.com', 'nestle.com', 'novartis.com',
        'roche.com', 'astrazeneca.com', 'gsk.com', 'sanofi.com', 'bayer.com',
        'toyota.com', 'honda.com', 'nissan.com', 'hyundai.com', 'kia.com',
        'ikea.com', 'hm.com', 'zara.com', 'adidas.com', 'puma.com',
        'lvmh.com', 'hermes.com', 'chanel.com', 'gucci.com', 'prada.com',
    ],
}


def generate_subdomains(base_domains: list, count: int) -> list:
    """Generate realistic subdomains."""
    prefixes = [
        'www', 'api', 'docs', 'dev', 'staging', 'beta', 'app', 'mail',
        'blog', 'cdn', 'static', 'assets', 'media', 'status', 'support',
        'admin', 'dashboard', 'portal', 'auth', 'login', 'sso', 'id',
        'data', 'analytics', 'metrics', 'monitor', 'logs', 'search',
        'store', 'shop', 'pay', 'billing', 'account', 'my', 'help',
        'forum', 'community', 'wiki', 'learn', 'academy', 'training',
        'careers', 'jobs', 'about', 'press', 'investor', 'ir',
    ]
    results = []
    for _ in range(count):
        prefix = random.choice(prefixes)
        base = random.choice(base_domains)
        results.append(f"{prefix}.{base}")
    return results


def generate_5000_seeds() -> list:
    """Generate 5000 diverse entity seeds."""
    seeds = []

    # 1. Real URLs (75)
    seeds.extend([('url', url) for url in SEED_URLS])

    # 2. Base domains from all categories (flattened + deduplicated)
    all_domains = []
    for category, domains in DOMAIN_POOLS.items():
        all_domains.extend(domains)
    all_domains = list(set(all_domains))
    random.shuffle(all_domains)

    seeds.extend([('domain', d) for d in all_domains])

    # 3. Generated subdomains to fill remaining
    remaining = 5000 - len(seeds)
    subdomains = generate_subdomains(all_domains, remaining + 500)  # extra for dedup
    subdomains = list(set(subdomains))[:remaining]
    seeds.extend([('domain', sd) for sd in subdomains])

    # Shuffle everything
    random.shuffle(seeds)

    return seeds[:5000]


def run_stress_test():
    """Execute the 5000-entity stress test."""
    db_path = "stress_test.db"

    # Clean slate
    if os.path.exists(db_path):
        os.remove(db_path)

    print("╔══════════════════════════════════════════════════════════╗")
    print("║         XP-ARC STRESS TEST — 5000 ENTITY GAUNTLET      ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print("║  Testing: Pool throughput, Aboyeur QA, Zoran's Law,    ║")
    print("║           SpaZzMatiC monitoring, station routing        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    # ─── Initialize ───
    pool = IntelligencePool(db_path)
    executive = ExecutiveChef(pool, max_entities=10000, verbose=False)
    zorans = ZoransLaw(pool)
    spazz = SpaZzMatiC(pool, zorans)

    # Stations — reduce timeouts for stress test
    forager = TheForager(pool, max_domains_per_target=3, timeout=4)
    analyst = TheAnalyst(pool)
    sentinel = TheSentinel(pool)
    plongeur = ThePlongeur(pool)

    # Override analyst probe timeout for speed
    analyst.sla_seconds = 10

    executive.register_station(forager)
    executive.register_station(analyst)

    # ─── Generate Seeds ───
    print("[GENERATE] Creating 5000 diverse entity seeds...")
    t_gen_start = time.time()
    seeds = generate_5000_seeds()
    t_gen = time.time() - t_gen_start
    print(f"[GENERATE] {len(seeds)} seeds generated in {t_gen:.2f}s")

    url_count = sum(1 for t, _ in seeds if t == 'url')
    domain_count = sum(1 for t, _ in seeds if t == 'domain')
    print(f"[GENERATE] {url_count} URLs + {domain_count} domains")
    print()

    # ─── Inject Seeds ───
    print("[INJECT] Seeding pool...")
    t_inject_start = time.time()
    injected = 0
    duplicates = 0
    for ent_type, value in seeds:
        result = pool.add_entity(ent_type, value)
        if result:
            injected += 1
        else:
            duplicates += 1

        if injected % 500 == 0 and injected > 0:
            print(f"  ... {injected} injected ({duplicates} duplicates skipped)")

    t_inject = time.time() - t_inject_start
    print(f"[INJECT] {injected} entities injected, {duplicates} duplicates. "
          f"Time: {t_inject:.2f}s ({injected/t_inject:.0f} entities/sec)")

    # Pre-injection Zoran measurement
    zorans.measure()
    print()

    # ─── Run Brigade ───
    print("[BRIGADE] Starting service... (this will take a while)")
    print(f"[BRIGADE] Processing {pool.count_entities()} entities through the pipeline")
    print()

    t_brigade_start = time.time()

    # Process in batches, measuring Zoran's every 500 entities
    batch = 0
    while True:
        raw = pool.get_next_raw()
        if not raw:
            break

        batch += 1
        summary = executive.run_service()

        # Periodic monitoring
        if batch % 10 == 0:
            measurement = zorans.measure()
            sentinel.run_health_check()
            review = spazz.run_review()

            completed = pool.get_stats().get('completed', {}).get('count', 0)
            total = pool.count_entities()
            elapsed = time.time() - t_brigade_start

            print(f"  [PROGRESS] {completed}/{total} completed | "
                  f"S={measurement['stability_quotient']:.3f} | "
                  f"PRO={measurement['primary_role_occupancy']:.0%} | "
                  f"State={measurement['system_state']} | "
                  f"{elapsed:.0f}s elapsed | "
                  f"{completed/max(elapsed,1):.1f} entities/sec")

            if review['safe_halt_recommended']:
                print("  [!!! SAFE HALT RECOMMENDED !!!]")

    t_brigade = time.time() - t_brigade_start

    # ─── Final Monitoring ───
    print()
    print("─" * 60)
    print("  POST-PROCESSING")
    print("─" * 60)

    plongeur.run_sweep()
    sentinel_findings = sentinel.run_health_check()
    final_zorans = zorans.measure()
    final_spazz = spazz.run_review()

    # ─── Results ───
    stats = pool.get_stats()
    entities = pool.get_all_entities()
    edges = pool.get_all_edges()
    findings = pool.get_findings()

    total_entities = len(entities)
    completed = stats.get('completed', {}).get('count', 0)
    failed = stats.get('failed', {}).get('count', 0)
    signed = sum(1 for e in entities if e['aboyeur_signature'])

    total_time = time.time() - t_gen_start

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║              STRESS TEST RESULTS                        ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║  Total Entities:     {total_entities:<37} ║")
    print(f"║  Completed:          {completed:<37} ║")
    print(f"║  Failed:             {failed:<37} ║")
    print(f"║  Aboyeur Signed:     {signed:<37} ║")
    print(f"║  Edges:              {len(edges):<37} ║")
    print(f"║  Findings:           {len(findings):<37} ║")
    print(f"║                                                        ║")
    print(f"║  Zoran S:            {final_zorans['stability_quotient']:<37} ║")
    print(f"║  Zoran PRO:          {final_zorans['primary_role_occupancy']:<37} ║")
    print(f"║  System State:       {final_zorans['system_state']:<37} ║")
    print(f"║                                                        ║")
    print(f"║  Safe Halt:          {'YES' if final_spazz['safe_halt_recommended'] else 'No':<37} ║")
    print(f"║                                                        ║")
    print(f"║  Seed Generation:    {t_gen:.2f}s{' ' * (34 - len(f'{t_gen:.2f}s'))} ║")
    print(f"║  Pool Injection:     {t_inject:.2f}s ({injected/t_inject:.0f}/sec){' ' * max(0, 24 - len(f'{t_inject:.2f}s ({injected/t_inject:.0f}/sec)'))} ║")
    print(f"║  Brigade Processing: {t_brigade:.2f}s ({completed/max(t_brigade,1):.1f}/sec){' ' * max(0, 22 - len(f'{t_brigade:.2f}s ({completed/max(t_brigade,1):.1f}/sec)'))} ║")
    print(f"║  Total Time:         {total_time:.2f}s{' ' * (34 - len(f'{total_time:.2f}s'))} ║")
    print("╚══════════════════════════════════════════════════════════╝")

    # ─── Aboyeur Stats ───
    aboyeur_stats = executive.aboyeur.stats
    print(f"\n[ ABOYEUR ]")
    print(f"  Verifications: {aboyeur_stats['verifications']}")
    print(f"  Approvals:     {aboyeur_stats['approvals']} ({aboyeur_stats['approval_rate']:.1%})")
    print(f"  Rejections:    {aboyeur_stats['rejections']} ({aboyeur_stats['rejection_rate']:.1%})")

    # ─── Station Stats ───
    print(f"\n[ STATIONS ]")
    for s in executive.stations:
        st = s.stats
        print(f"  {st['name']:<20} Processed: {st['processed']:<8} Failed: {st['failed']}")

    # ─── Entity Type Distribution ───
    type_dist = {}
    for e in entities:
        type_dist[e['type']] = type_dist.get(e['type'], 0) + 1
    print(f"\n[ ENTITY TYPES ]")
    for t, c in sorted(type_dist.items(), key=lambda x: -x[1]):
        print(f"  {t:<20} {c}")

    # ─── Status Distribution ───
    print(f"\n[ STATUS DISTRIBUTION ]")
    for status, info in sorted(stats.items()):
        pct = info['count'] / max(total_entities, 1) * 100
        bar = '█' * int(pct / 2) + '░' * (50 - int(pct / 2))
        print(f"  {status:<15} {info['count']:>6} ({pct:>5.1f}%) {bar}")

    # ─── SpaZzMatiC Summary ───
    if findings:
        print(f"\n[ SPAZZMATIC FINDINGS ({len(findings)}) ]")
        for f in findings[:20]:
            print(f"  [{f['severity'].upper():>8}] {f['message'][:70]}")
        if len(findings) > 20:
            print(f"  ... and {len(findings) - 20} more")

    # ─── Export for DRAGON ───
    export = pool.export_state()
    export['summary'] = executive.summary()
    export['zorans_latest'] = final_zorans
    export['stress_test'] = {
        'total_seeds': len(seeds),
        'injected': injected,
        'duplicates': duplicates,
        'total_time_seconds': total_time,
        'brigade_time_seconds': t_brigade,
        'throughput_entities_per_sec': completed / max(t_brigade, 1),
    }

    export_path = db_path.replace('.db', '_dragon.json')
    with open(export_path, 'w') as f:
        json.dump(export, f, indent=2, default=str)
    print(f"\n[DRAGON] Exported to {export_path}")

    pool.close()
    return export


if __name__ == '__main__':
    run_stress_test()
