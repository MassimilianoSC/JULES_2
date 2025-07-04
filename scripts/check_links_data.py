from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
from pprint import pprint

async def main():
    # Connessione al database
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.intranet
    
    print("\n=== Verifica struttura dati links ===")
    links = await db.links.find({}).to_list(None)
    for link in links:
        print("\nLink:")
        print(f"Titolo: {link.get('title')}")
        print(f"Employment Type: {link.get('employment_type')}")
        print(f"Branch: {link.get('branch')}")
        print(f"Show on home: {link.get('show_on_home', False)}")
    
    print("\n=== Verifica struttura dati home_highlights ===")
    highlights = await db.home_highlights.find({"type": "link"}).to_list(None)
    for highlight in highlights:
        print("\nHighlight:")
        print(f"Object ID: {highlight.get('object_id')}")
        print(f"Employment Type: {highlight.get('employment_type')}")
        print(f"Branch: {highlight.get('branch')}")

    # Verifica coerenza tra le collezioni
    print("\n=== Verifica coerenza tra collezioni ===")
    for link in links:
        if link.get('show_on_home'):
            highlight = await db.home_highlights.find_one({
                "type": "link",
                "object_id": str(link['_id'])
            })
            print(f"\nLink '{link.get('title')}' dovrebbe essere in home:")
            if highlight:
                print("✅ Trovato in home_highlights")
                # Verifica coerenza dei campi
                if highlight.get('employment_type') != link.get('employment_type'):
                    print("❌ Discrepanza in employment_type:")
                    print(f"  Links: {link.get('employment_type')}")
                    print(f"  Highlights: {highlight.get('employment_type')}")
                if highlight.get('branch') != link.get('branch'):
                    print("❌ Discrepanza in branch:")
                    print(f"  Links: {link.get('branch')}")
                    print(f"  Highlights: {highlight.get('branch')}")
            else:
                print("❌ Non trovato in home_highlights!")

if __name__ == "__main__":
    asyncio.run(main()) 