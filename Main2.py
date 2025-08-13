import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import aiohttp
import random
import string
import asyncio
from aiohttp import web

TOKEN = "MTQwNTI5NzIzMjAyMTk0NjM3OA.GPwupC.4703A9GYpmxcsG-U_5FaeHPf85gLiWFivuyOCM"
WHITELIST_FILE = "whitelist.json"
LINK_FILE = "linked_accounts.json"
VERIFY_FILE = "pending_verifications.json"
PRODUCTS_FILE = "Products.json"

# Role ID that is allowed to manage products
MANAGER_ROLE_ID = 1404532270622310400  # <-- replace with your role ID

# ---------- Helper functions ----------
def load_json(filename):
    # create file if missing
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump([], f)
    # create empty list if file empty
    if os.path.getsize(filename) == 0:
        with open(filename, "w") as f:
            json.dump([], f)
    with open(filename, "r") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

# Initialize Products.json with some default products if empty
products = load_json(PRODUCTS_FILE)
if not products:
    products = ["TestProduct1", "TestProduct2"]
    save_json(PRODUCTS_FILE, products)

# ---------- Roblox API helpers ----------
async def get_roblox_user_id(username: str):
    url = "https://users.roblox.com/v1/usernames/users"
    payload = {"usernames": [username], "excludeBannedUsers": True}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if "data" in data and len(data["data"]) > 0:
                    return data["data"][0]["id"]
                return None
    except aiohttp.ClientError:
        return None

async def get_roblox_description(user_id: int):
    url = f"https://users.roblox.com/v1/users/{user_id}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("description", "")
    except aiohttp.ClientError:
        return None

# ---------- Discord Bot ----------
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- Link & Verify Cog ----------
class LinkCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="linkroblox", description="Start linking your Roblox account")
    async def linkroblox(self, interaction: discord.Interaction, roblox_username: str):
        await interaction.response.defer(ephemeral=True)
        roblox_id = await get_roblox_user_id(roblox_username)
        if not roblox_id:
            await interaction.followup.send("❌ Could not find that Roblox username.")
            return

        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        pending = load_json(VERIFY_FILE)
        pending = [p for p in pending if p.get("discordId") != str(interaction.user.id)]
        pending.append({
            "discordId": str(interaction.user.id),
            "robloxId": str(roblox_id),
            "robloxUsername": roblox_username,
            "code": code
        })
        save_json(VERIFY_FILE, pending)

        await interaction.followup.send(
            f"🔒 Verification Step:\n"
            f"1. Go to your Roblox profile: https://www.roblox.com/users/{roblox_id}/profile\n"
            f"2. Edit your **About/Description**.\n"
            f"3. Add this code somewhere in it: **{code}**\n"
            f"4. Then run /verifyroblox to finish linking."
        )

    @app_commands.command(name="verifyroblox", description="Verify your Roblox account after placing the code in your profile")
    async def verifyroblox(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        pending = load_json(VERIFY_FILE)
        entry = next((p for p in pending if p.get("discordId") == str(interaction.user.id)), None)
        if not entry:
            await interaction.followup.send("⚠ You don’t have a pending verification. Run /linkroblox first.")
            return

        description = await get_roblox_description(int(entry["robloxId"]))
        if not description:
            await interaction.followup.send("❌ Could not fetch your Roblox profile. Try again later.")
            return

        if entry["code"] in description:
            linked_accounts = load_json(LINK_FILE)
            linked_accounts = [acc for acc in linked_accounts if acc.get("discordId") != str(interaction.user.id)]
            linked_accounts.append({
                "discordId": entry["discordId"],
                "robloxId": entry["robloxId"],
                "robloxUsername": entry["robloxUsername"],
                "discordName": str(interaction.user),
                "ownedProducts": []
            })
            save_json(LINK_FILE, linked_accounts)

            whitelist = load_json(WHITELIST_FILE)
            found = False
            for user in whitelist:
                if user.get("discordId") == str(interaction.user.id):
                    user["robloxId"] = entry["robloxId"]
                    user["robloxUsername"] = entry["robloxUsername"]
                    user["discordName"] = str(interaction.user)
                    user["ownedProducts"] = []
                    found = True
            if not found:
                whitelist.append({
                    "discordId": entry["discordId"],
                    "discordName": str(interaction.user),
                    "robloxId": entry["robloxId"],
                    "robloxUsername": entry["robloxUsername"],
                    "ownedProducts": []
                })
            save_json(WHITELIST_FILE, whitelist)

            pending = [p for p in pending if p.get("discordId") != str(interaction.user.id)]
            save_json(VERIFY_FILE, pending)

            await interaction.followup.send(f"✅ Successfully linked to Roblox account **{entry['robloxUsername']}**.")
        else:
            await interaction.followup.send("❌ Code not found in your profile description. Make sure it’s visible and try again.")

    @app_commands.command(name="unlinkroblox", description="Unlink your Roblox account from Discord")
    async def unlinkroblox(self, interaction: discord.Interaction):
        linked_accounts = load_json(LINK_FILE)
        if not any(acc.get("discordId") == str(interaction.user.id) for acc in linked_accounts):
            await interaction.response.send_message(
                "⚠ You don't have a linked Roblox account.", ephemeral=True
            )
            return

        linked_accounts = [acc for acc in linked_accounts if acc.get("discordId") != str(interaction.user.id)]
        save_json(LINK_FILE, linked_accounts)

        whitelist = load_json(WHITELIST_FILE)
        for user in whitelist:
            if user.get("discordId") == str(interaction.user.id):
                user["robloxId"] = None
                user["robloxUsername"] = None
                user["ownedProducts"] = []
        save_json(WHITELIST_FILE, whitelist)

        await interaction.response.send_message(
            "✅ Your Roblox account has been successfully unlinked.", ephemeral=True
        )

# ---------- Product Management Cog ----------
class ProductCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def has_manager_role(self, member: discord.Member):
        return any(role.id == MANAGER_ROLE_ID for role in member.roles)

    @app_commands.command(name="createproduct", description="Create a new product")
    async def createproduct(self, interaction: discord.Interaction, product_name: str):
        if not self.has_manager_role(interaction.user):
            await interaction.response.send_message("❌ You don’t have permission to create products.", ephemeral=True)
            return

        products = load_json(PRODUCTS_FILE)
        if product_name in products:
            await interaction.response.send_message(f"⚠ Product **{product_name}** already exists.", ephemeral=True)
            return
        products.append(product_name)
        save_json(PRODUCTS_FILE, products)

        await interaction.response.send_message(f"✅ Product **{product_name}** has been created.", ephemeral=False)

    @app_commands.command(name="deleteproduct", description="Delete an existing product")
    async def deleteproduct(self, interaction: discord.Interaction, product_name: str):
        if not self.has_manager_role(interaction.user):
            await interaction.response.send_message("❌ You don’t have permission to delete products.", ephemeral=True)
            return

        products = load_json(PRODUCTS_FILE)
        if product_name not in products:
            await interaction.response.send_message(f"⚠ Product **{product_name}** does not exist.", ephemeral=True)
            return
        products.remove(product_name)
        save_json(PRODUCTS_FILE, products)

        linked_accounts = load_json(LINK_FILE)
        for acc in linked_accounts:
            if product_name in acc.get("ownedProducts", []):
                acc["ownedProducts"].remove(product_name)
        save_json(LINK_FILE, linked_accounts)

        whitelist = load_json(WHITELIST_FILE)
        for user in whitelist:
            if product_name in user.get("ownedProducts", []):
                user["ownedProducts"].remove(product_name)
        save_json(WHITELIST_FILE, whitelist)

        await interaction.response.send_message(f"✅ Product **{product_name}** has been deleted.", ephemeral=False)

    @app_commands.command(name="addproduct", description="Add a product to a user")
    async def addproduct(self, interaction: discord.Interaction, target: discord.User, product_name: str):
        if not self.has_manager_role(interaction.user):
            await interaction.response.send_message("❌ You don’t have permission to add products.", ephemeral=True)
            return

        products = load_json(PRODUCTS_FILE)
        if product_name not in products:
            await interaction.response.send_message(f"⚠ Product **{product_name}** does not exist. Create it first.", ephemeral=True)
            return

        linked_accounts = load_json(LINK_FILE)
        acc = next((a for a in linked_accounts if a.get("discordId") == str(target.id)), None)
        if not acc:
            await interaction.response.send_message(f"❌ Target user **{target}** does not have a linked Roblox account.", ephemeral=True)
            return
        if product_name not in acc["ownedProducts"]:
            acc["ownedProducts"].append(product_name)
        save_json(LINK_FILE, linked_accounts)

        whitelist = load_json(WHITELIST_FILE)
        for user in whitelist:
            if user.get("discordId") == str(target.id):
                if product_name not in user["ownedProducts"]:
                    user["ownedProducts"].append(product_name)
        save_json(WHITELIST_FILE, whitelist)

        await interaction.response.send_message(f"✅ Added **{product_name}** to {target}.", ephemeral=False)

    @app_commands.command(name="removeproduct", description="Remove a product from a user")
    async def removeproduct(self, interaction: discord.Interaction, target: discord.User, product_name: str):
        if not self.has_manager_role(interaction.user):
            await interaction.response.send_message("❌ You don’t have permission to remove products.", ephemeral=True)
            return

        linked_accounts = load_json(LINK_FILE)
        acc = next((a for a in linked_accounts if a.get("discordId") == str(target.id)), None)
        if not acc:
            await interaction.response.send_message(f"❌ Target user **{target}** does not have a linked Roblox account.", ephemeral=True)
            return
        if product_name in acc.get("ownedProducts", []):
            acc["ownedProducts"].remove(product_name)
        save_json(LINK_FILE, linked_accounts)

        whitelist = load_json(WHITELIST_FILE)
        for user in whitelist:
            if product_name in user.get("ownedProducts", []):
                user["ownedProducts"].remove(product_name)
        save_json(WHITELIST_FILE, whitelist)

        await interaction.response.send_message(f"✅ Removed **{product_name}** from {target}.", ephemeral=False)

# ---------- Whitelist Cog ----------
class WhitelistCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Check whitelist info of a specific user")
    @app_commands.describe(user="Select the Discord user to check")
    async def listwl(self, interaction: discord.Interaction, user: discord.User):
        whitelist = load_json(WHITELIST_FILE)
        linked_accounts = load_json(LINK_FILE)

        wl_user = next((u for u in whitelist if u.get("discordId") == str(user.id)), None)
        linked = next((acc for acc in linked_accounts if acc.get("discordId") == str(user.id)), None)

        discord_name = linked.get("discordName") if linked else (wl_user.get("discordName") if wl_user else None)
        roblox_username = linked.get("robloxUsername") if linked else (wl_user.get("robloxUsername") if wl_user else None)
        products = linked.get("ownedProducts") if linked else (wl_user.get("ownedProducts") if wl_user else [])

        if not discord_name and not roblox_username:
            await interaction.response.send_message("❌ User not found in whitelist.", ephemeral=False)
            return

        msg = f"**Whitelist Info for {discord_name}:**\n"
        msg += f"- Roblox: {roblox_username or 'Not linked'}\n"
        msg += f"- Owned Products: {', '.join(products) if products else 'None'}"
        await interaction.response.send_message(msg, ephemeral=False)

# ---------- Bot Setup ----------
@bot.event
async def on_ready():
    await bot.add_cog(LinkCog(bot))
    await bot.add_cog(ProductCog(bot))
    await bot.add_cog(WhitelistCog(bot))
    await bot.tree.sync()
    print(f"✅ Bot ready as {bot.user}")

bot.run(TOKEN)
