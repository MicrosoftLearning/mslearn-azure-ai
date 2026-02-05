"""
Generate sample vector data for the Cosmos DB index comparison exercise.
Creates 500 support ticket documents with 256-dimensional embeddings.
"""
import json
import random

# Categories and their associated content templates
CATEGORIES = {
    "billing": {
        "priority_weights": {"high": 0.3, "medium": 0.5, "low": 0.2},
        "tags_pool": ["refund", "charge", "invoice", "subscription", "payment", "pricing", "discount", "credit"],
        "templates": [
            "I was charged ${amount} twice for my {plan} subscription on {date}. Please refund the duplicate charge.",
            "My invoice shows incorrect pricing. I signed up for the ${promo_price} promotional rate but was billed ${actual_price}.",
            "I cancelled my subscription on {date} but continue to receive charges. Please stop billing and issue a refund.",
            "Need a detailed receipt for my company's expense report. Transaction on {date} for ${amount}.",
            "The automatic payment failed and now my account shows a late fee. My card ending in {card_last4} should be valid.",
            "I was promised a {percent}% discount but it wasn't applied to my last invoice of ${amount}.",
            "Please update my billing address to {address}. The current invoices are going to the wrong location.",
            "My annual subscription renewed at ${amount} but I wanted to switch to monthly billing at ${monthly_price}.",
            "I need to split the ${amount} payment into installments. Is there a payment plan available?",
            "The currency conversion on my international card resulted in unexpected fees totaling ${amount}.",
        ]
    },
    "technical": {
        "priority_weights": {"high": 0.4, "medium": 0.4, "low": 0.2},
        "tags_pool": ["login", "password", "crash", "error", "performance", "sync", "update", "connection", "api", "timeout"],
        "templates": [
            "Cannot login to my account. Getting '{error_msg}' error even though my password is correct.",
            "The {platform} app crashes whenever I open the {feature} page. Started after the latest update.",
            "My {device} won't connect to the {service}. Shows green light but devices don't appear in the app.",
            "Website is extremely slow when uploading files over {size}MB. My connection is {speed} Mbps.",
            "Two-factor authentication codes from the authenticator app aren't working. Always shows 'Invalid code'.",
            "API requests are returning {error_code} errors intermittently. About {percent}% of requests fail.",
            "Data sync between {device1} and {device2} stopped working {time_ago}. Manual sync doesn't help.",
            "The {feature} feature is missing after the update to version {version}. Where did it go?",
            "Getting timeout errors when trying to {action}. The operation never completes.",
            "Push notifications stopped working on my {device} running {os_version}. Settings look correct.",
            "The search function returns no results even for exact matches. Indexing seems broken.",
            "Video calls keep dropping after {minutes} minutes. Audio works fine but video freezes.",
        ]
    },
    "account": {
        "priority_weights": {"high": 0.35, "medium": 0.45, "low": 0.2},
        "tags_pool": ["profile", "email", "security", "password", "2fa", "deletion", "privacy", "permissions", "verification"],
        "templates": [
            "Need to update my email from {old_email} to {new_email}. The old one is no longer accessible.",
            "I want to delete my account and all data in compliance with {regulation} regulations.",
            "Someone tried to access my account from {location}. Please help secure it immediately.",
            "Need to add a second user to my business account. Their email is {email} and they need {role} access.",
            "My account was locked after {attempts} failed login attempts. I need to regain access.",
            "Please merge my two accounts: {email1} and {email2}. I accidentally created a duplicate.",
            "I need to change my username from {old_name} to {new_name}. Is this possible?",
            "Export all my personal data as required by {regulation}. I need it in {format} format.",
            "The verification email never arrives at {email}. I've checked spam and waited {hours} hours.",
            "My profile photo keeps reverting to the default after I upload a new one.",
            "Need to transfer account ownership to {email}. I'm leaving the organization.",
            "The account recovery questions aren't ones I set. I think someone changed my security settings.",
        ]
    },
    "shipping": {
        "priority_weights": {"high": 0.35, "medium": 0.45, "low": 0.2},
        "tags_pool": ["delivery", "tracking", "address", "missing", "damaged", "return", "expedited", "international"],
        "templates": [
            "Package marked delivered on {date} but I never received it. Tracking shows left at {location}.",
            "Need to change shipping address for order #{order_id}. New address is {address}.",
            "Order stuck in transit since {date}. Tracking hasn't updated in {days} days. Paid for expedited shipping.",
            "Received wrong item. Ordered {ordered_item} but received {received_item} instead.",
            "Package arrived damaged. The {item} inside is {damage_description}. Need replacement.",
            "What's the estimated delivery for order #{order_id}? It's been {days} days with no update.",
            "Need to return {item} from order #{order_id}. It doesn't fit/work as expected.",
            "Can I pick up my package at a local {carrier} location instead of home delivery?",
            "International shipment to {country} is stuck in customs since {date}. Any documentation needed?",
            "The delivery driver couldn't find my address. Please add these instructions: {instructions}.",
            "My package was delivered to the wrong apartment ({wrong_apt}) instead of mine ({correct_apt}).",
            "Need to schedule a specific delivery window. I'm only home between {start_time} and {end_time}.",
        ]
    },
    "product": {
        "priority_weights": {"high": 0.2, "medium": 0.5, "low": 0.3},
        "tags_pool": ["quality", "defective", "warranty", "replacement", "parts", "compatibility", "features", "manual"],
        "templates": [
            "Product quality is disappointing. The {material} feels cheap and {defect} after {time_period} of use.",
            "Looking for replacement parts for {product_model}. Specifically need {part_name}.",
            "Is {product} compatible with {other_product}? Need to know before purchasing.",
            "The {feature} feature doesn't work as described in the product listing.",
            "My {product} stopped working after {time_period}. It's still under warranty until {warranty_date}.",
            "Where can I find the user manual for {product_model}? Can't find it on the website.",
            "The {product} makes a {sound_description} noise during operation. Is this normal?",
            "Need to know the exact dimensions of {product} including packaging for storage planning.",
            "Can the {product} be used outdoors? The specifications don't mention water resistance.",
            "The color of the {product} received doesn't match the photos. Expected {expected_color}, got {actual_color}.",
            "Battery life on my {product} is only {actual_hours} hours, not the advertised {advertised_hours} hours.",
            "Is there a software update available for {product_model}? Current version is {version}.",
        ]
    }
}

# Query templates for testing
QUERY_TEMPLATES = [
    {"id": "query-login-issue", "description": "I can't login to my account"},
    {"id": "query-double-charge", "description": "My payment was charged twice"},
    {"id": "query-missing-package", "description": "Package hasn't arrived yet"},
    {"id": "query-account-security", "description": "Protect my account from hackers"},
    {"id": "query-product-broken", "description": "My product stopped working"},
    {"id": "query-refund-request", "description": "I need a refund for my order"},
    {"id": "query-app-crash", "description": "The mobile app keeps crashing"},
    {"id": "query-change-address", "description": "Update my shipping address"},
]

def generate_embedding(dim=256, seed=None):
    """Generate a random normalized embedding vector."""
    if seed:
        random.seed(seed)
    # Generate random values
    vec = [random.uniform(-1, 1) for _ in range(dim)]
    # Normalize to unit length (approximation for cosine similarity)
    magnitude = sum(v**2 for v in vec) ** 0.5
    return [round(v / magnitude, 3) for v in vec]

def fill_template(template, category):
    """Fill a template with random realistic values."""
    replacements = {
        "{amount}": str(random.randint(10, 500)),
        "{plan}": random.choice(["Basic", "Pro", "Enterprise", "Premium", "Starter"]),
        "{date}": f"{random.choice(['January', 'February', 'March'])} {random.randint(1, 28)}",
        "{promo_price}": str(random.randint(9, 29)),
        "{actual_price}": str(random.randint(30, 99)),
        "{card_last4}": str(random.randint(1000, 9999)),
        "{percent}": str(random.randint(10, 50)),
        "{address}": f"{random.randint(100, 999)} {random.choice(['Oak', 'Maple', 'Pine', 'Cedar'])} Street, {random.choice(['Chicago', 'Austin', 'Seattle', 'Boston'])}",
        "{monthly_price}": str(random.randint(9, 29)),
        "{error_msg}": random.choice(["Invalid credentials", "Account locked", "Session expired", "Authentication failed"]),
        "{platform}": random.choice(["iOS", "Android", "Windows", "macOS", "web"]),
        "{feature}": random.choice(["settings", "dashboard", "profile", "notifications", "search", "reports"]),
        "{device}": random.choice(["iPhone", "Android phone", "iPad", "laptop", "smart speaker", "smart TV"]),
        "{service}": random.choice(["hub", "cloud service", "Bluetooth", "WiFi network", "server"]),
        "{size}": str(random.randint(10, 100)),
        "{speed}": str(random.randint(100, 1000)),
        "{error_code}": random.choice(["500", "503", "504", "429", "403"]),
        "{device1}": random.choice(["phone", "tablet", "desktop"]),
        "{device2}": random.choice(["cloud", "laptop", "backup drive"]),
        "{time_ago}": random.choice(["yesterday", "last week", "3 days ago", "since the update"]),
        "{version}": f"{random.randint(2, 5)}.{random.randint(0, 9)}.{random.randint(0, 9)}",
        "{action}": random.choice(["save changes", "upload files", "export data", "generate reports"]),
        "{os_version}": random.choice(["iOS 17", "iOS 18", "Android 14", "Android 15"]),
        "{minutes}": str(random.randint(5, 30)),
        "{old_email}": f"user{random.randint(1, 999)}@oldcompany.com",
        "{new_email}": f"user{random.randint(1, 999)}@newcompany.com",
        "{email}": f"colleague{random.randint(1, 999)}@company.com",
        "{email1}": f"account1_{random.randint(1, 99)}@email.com",
        "{email2}": f"account2_{random.randint(1, 99)}@email.com",
        "{regulation}": random.choice(["GDPR", "CCPA", "privacy"]),
        "{role}": random.choice(["admin", "editor", "viewer", "manager"]),
        "{attempts}": str(random.randint(3, 10)),
        "{old_name}": f"user{random.randint(1000, 9999)}",
        "{new_name}": f"newuser{random.randint(1000, 9999)}",
        "{format}": random.choice(["JSON", "CSV", "PDF"]),
        "{hours}": str(random.randint(2, 48)),
        "{location}": random.choice(["front door", "mailroom", "neighbor", "porch", "locker"]),
        "{order_id}": f"{random.randint(100000, 999999)}",
        "{days}": str(random.randint(3, 14)),
        "{ordered_item}": random.choice(["blue keyboard", "wireless mouse", "USB-C cable", "laptop stand"]),
        "{received_item}": random.choice(["black mouse", "wired keyboard", "HDMI cable", "phone stand"]),
        "{item}": random.choice(["keyboard", "headphones", "monitor", "chair", "desk lamp"]),
        "{damage_description}": random.choice(["cracked", "scratched", "dented", "broken", "not working"]),
        "{carrier}": random.choice(["FedEx", "UPS", "USPS", "DHL"]),
        "{country}": random.choice(["Canada", "UK", "Germany", "Japan", "Australia"]),
        "{instructions}": random.choice(["use side entrance", "call on arrival", "leave at front desk"]),
        "{wrong_apt}": f"{random.randint(1, 10)}{random.choice(['A', 'B', 'C'])}",
        "{correct_apt}": f"{random.randint(1, 10)}{random.choice(['A', 'B', 'C'])}",
        "{start_time}": f"{random.randint(8, 12)}:00 AM",
        "{end_time}": f"{random.randint(1, 6)}:00 PM",
        "{material}": random.choice(["plastic", "fabric", "metal", "leather"]),
        "{defect}": random.choice(["started peeling", "came apart", "cracked", "discolored"]),
        "{time_period}": random.choice(["one week", "two weeks", "a month", "three months"]),
        "{product_model}": random.choice(["CM-2000", "XR-500", "Pro-Max", "Elite-V2", "Basic-100"]),
        "{product}": random.choice(["headphones", "speaker", "keyboard", "mouse", "monitor"]),
        "{other_product}": random.choice(["MacBook Pro", "Windows PC", "iPhone", "Android tablet"]),
        "{part_name}": random.choice(["power adapter", "cable", "battery", "filter", "cover"]),
        "{warranty_date}": f"{random.choice(['March', 'June', 'September', 'December'])} 2026",
        "{sound_description}": random.choice(["clicking", "buzzing", "humming", "rattling"]),
        "{expected_color}": random.choice(["navy blue", "forest green", "charcoal gray"]),
        "{actual_color}": random.choice(["light blue", "olive", "dark black"]),
        "{actual_hours}": str(random.randint(2, 6)),
        "{advertised_hours}": str(random.randint(8, 12)),
    }

    result = template
    for key, value in replacements.items():
        result = result.replace(key, value)
    return result

def generate_documents(count=500):
    """Generate a list of sample documents."""
    documents = []
    categories = list(CATEGORIES.keys())

    for i in range(count):
        category = categories[i % len(categories)]
        cat_data = CATEGORIES[category]

        # Select priority based on weights
        priority = random.choices(
            list(cat_data["priority_weights"].keys()),
            weights=list(cat_data["priority_weights"].values())
        )[0]

        # Select random tags
        tags = random.sample(cat_data["tags_pool"], k=random.randint(2, 4))

        # Generate content from template
        template = random.choice(cat_data["templates"])
        content = fill_template(template, category)

        doc_num = (i // len(categories)) + 1
        document_id = f"doc-{category}-{doc_num:03d}"
        chunk_id = f"{document_id}-chunk-0"

        # Generate embedding with seed based on content for some consistency
        embedding = generate_embedding(256, seed=hash(content) % 2**32)

        documents.append({
            "document_id": document_id,
            "chunk_id": chunk_id,
            "content": content,
            "metadata": {
                "source": "support-portal",
                "category": category,
                "priority": priority,
                "tags": tags,
                "chunkIndex": 0
            },
            "embedding": embedding
        })

    return documents

def generate_queries():
    """Generate query embeddings."""
    queries = []
    for q in QUERY_TEMPLATES:
        queries.append({
            "id": q["id"],
            "description": q["description"],
            "embedding": generate_embedding(256, seed=hash(q["description"]) % 2**32)
        })
    return queries

def main():
    print("Generating 500 sample documents...")
    documents = generate_documents(500)
    queries = generate_queries()

    data = {
        "documents": documents,
        "queries": queries
    }

    output_file = "sample_vectors.json"
    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Generated {len(documents)} documents and {len(queries)} queries")
    print(f"Saved to {output_file}")

    # Print category distribution
    from collections import Counter
    categories = Counter(d["metadata"]["category"] for d in documents)
    print("\nCategory distribution:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")

if __name__ == "__main__":
    main()
