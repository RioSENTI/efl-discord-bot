import os
import psycopg2
import discord
from discord import app_commands
from discord.ext import commands
import json
import aiohttp

# ---------------- CONFIG ---------------- #

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

GUILD_ID = 1507809911437000837  # your Discord server ID

CHANNELS = {
    "announcements": 1507838489587224576,
    "freeagency": 1507870807479812197,
    "results": 1507837429430620241,
    "signings": 1507838212687790203,
    "releases": 1507838227996737587,
    "logs": 1510724073037238354,
}

TEAM_OWNERS = {
    1507834353760207029: "Everton",
    1507834328716152922: "West Brom",
    1507845725718052995: "Reading FC",
    1507834296680054784: "Liverpool FC",
}

TEAM_ROLES = {
    "Everton": 1507834353760207029,
    "West Brom": 1507834328716152922,
    "Reading FC": 1507845725718052995,
    "Liverpool FC": 1507834296680054784,
}

FREE_AGENT_ROLE = 1507834208343556117

ROLE_PERMS = {
    "admin_ops": [
        1507834721030246461,
        1507834677413679164,
        1508543351333453957,
        1507834667997462548,
        1507834620492779631,
        1507834517396652082,
    ],
    "team_ops": [
        1507834469057302590,
        1507834431350767817,
        1507834392976818326,
    ],
}

INITIAL_MONEY = {
    "Everton": 1526,
    "West Brom": 15622,
    "Reading FC": 11935,
    "Liverpool FC": 22126,
}

DATA_FILE = "data.json"

# ---------------- BOT SETUP ---------------- #

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- DATA ---------------- #

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {"money": INITIAL_MONEY}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)



# ---------------- HELPERS ---------------- #

def get_team_by_owner(member: discord.Member):
    for role in member.roles:
        if role.id in TEAM_OWNERS:
            return TEAM_OWNERS[role.id]
    return None


def has_role(member, role_ids):
    return any(role.id in role_ids for role in member.roles)


def add_money(team, amount):
    cursor.execute("""
        INSERT INTO money (team, balance)
        VALUES (%s, %s)
        ON CONFLICT (team)
        DO UPDATE SET balance = money.balance + %s
    """, (team, amount, amount))
    conn.commit()


async def roblox_headshot(username: str):
    url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?username={username}&size=420x420&format=Png&isCircular=false"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                js = await resp.json()
                return js["data"][0]["imageUrl"]
    
    return None

# ---------------- COMMANDS ---------------- #

@bot.tree.command(name="money", guild=discord.Object(id=GUILD_ID))
async def money(interaction: discord.Interaction):
    team = get_team_by_owner(interaction.user)

    if not team:
        return await interaction.response.send_message("No team found.", ephemeral=True)

    cursor.execute("SELECT balance FROM money WHERE team = %s", (team,))
    result = cursor.fetchone()

    balance = result[0] if result else 0

    await interaction.response.send_message(f"💰 {team} Balance: ${balance}")

# ---------------- SIGN ---------------- #

@bot.tree.command(name="sign", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(player="Player", team="Team")
async def sign(interaction: discord.Interaction, player: discord.Member, team: str):

    if not has_role(interaction.user, ROLE_PERMS["team_ops"]):
        return await interaction.response.send_message("No permission.", ephemeral=True)

    team = team.title()
    if team not in TEAM_ROLES:
        return await interaction.response.send_message("Invalid team.", ephemeral=True)

    guild = interaction.guild
    role = guild.get_role(TEAM_ROLES[team])
    fa_role = guild.get_role(FREE_AGENT_ROLE)

    await player.add_roles(role)
    await player.remove_roles(fa_role)

    channel = guild.get_channel(CHANNELS["signings"])

    embed = discord.Embed(
        title="✍️ Signing",
        description=f"{player.mention} signed for **{team}**",
        color=discord.Color.green()
    )

    await channel.send(embed=embed)
    await interaction.response.send_message("Signed successfully.", ephemeral=True)
    
# ---------------- ADD MONEY ---------------- #

@bot.tree.command(name="addmoney", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(team="Team name", amount="Amount to add")
async def addmoney(
    interaction: discord.Interaction,
    team: str,
    amount: int
):

    # admin permission check
    if not has_role(interaction.user, ROLE_PERMS["admin_ops"]):
        return await interaction.response.send_message(
            "No permission.",
            ephemeral=True
        )

    team = team.title()

    cursor.execute("""
        INSERT INTO money (team, balance)
        VALUES (%s, %s)
        ON CONFLICT (team)
        DO UPDATE SET balance = money.balance + %s
    """, (team, amount, amount))

    conn.commit()

    cursor.execute(
        "SELECT balance FROM money WHERE team = %s",
        (team,)
    )

    result = cursor.fetchone()
    balance = result[0] if result else 0

    await interaction.response.send_message(
        f"💰 Added ${amount:,} to **{team}**\nNew Balance: ${balance:,}",
        ephemeral=True
    )

# ---------------- REMOVE MONEY ---------------- #

@bot.tree.command(name="removemoney", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(team="Team name", amount="Amount to remove")
async def removemoney(
    interaction: discord.Interaction,
    team: str,
    amount: int
):

    # admin permission check
    if not has_role(interaction.user, ROLE_PERMS["admin_ops"]):
        return await interaction.response.send_message(
            "No permission.",
            ephemeral=True
        )

    team = team.title()

    # subtract money
    cursor.execute("""
        INSERT INTO money (team, balance)
        VALUES (%s, 0)
        ON CONFLICT (team)
        DO UPDATE SET balance = money.balance - %s
    """, (team, amount))

    conn.commit()

    # get updated balance
    cursor.execute(
        "SELECT balance FROM money WHERE team = %s",
        (team,)
    )

    result = cursor.fetchone()
    balance = result[0] if result else 0

    await interaction.response.send_message(
        f"💸 Removed ${amount:,} from **{team}**\nNew Balance: ${balance:,}",
        ephemeral=True
    )

# ---------------- RELEASE ---------------- #

@bot.tree.command(name="release", guild=discord.Object(id=GUILD_ID))
async def release(interaction: discord.Interaction, player: discord.Member, reason: str):

    if not has_role(interaction.user, ROLE_PERMS["team_ops"]):
        return await interaction.response.send_message("No permission.", ephemeral=True)

    guild = interaction.guild

    for team, role_id in TEAM_ROLES.items():
        role = guild.get_role(role_id)
        if role in player.roles:
            await player.remove_roles(role)

    fa_role = guild.get_role(FREE_AGENT_ROLE)
    await player.add_roles(fa_role)

    channel = guild.get_channel(CHANNELS["releases"])

    embed = discord.Embed(
        title="🚪 Release",
        description=f"{player.mention} released\nReason: {reason}",
        color=discord.Color.red()
    )

    await channel.send(embed=embed)
    await interaction.response.send_message("Player released.", ephemeral=True)

# ---------------- MONEY LEND ---------------- #

@bot.tree.command(name="moneylend", guild=discord.Object(id=GUILD_ID))
async def moneylend(interaction: discord.Interaction, team: str, amount: int):

    if not has_role(interaction.user, ROLE_PERMS["team_ops"]):
        return await interaction.response.send_message("No permission.", ephemeral=True)

    team = team.title()

    add_money(team, amount)

    await interaction.response.send_message(f"{team} received ${amount}")
    
# ---------------- NEGOTIATE ---------------- #

class NegotiationView(discord.ui.View):
    def __init__(self, seller_team, buyer_team, player: discord.Member, amount: int, manager: discord.Member):
        super().__init__(timeout=300)

        self.seller_team = seller_team
        self.buyer_team = buyer_team
        self.player = player
        self.amount = amount
        self.manager = manager

        self.finished = False
        self.player_roles = [r.id for r in player.roles]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.manager:
            await interaction.response.send_message(
                "❌ You are not allowed to respond to this negotiation.",
                ephemeral=True
            )
            return False

        if self.finished:
            await interaction.response.send_message(
                "❌ This negotiation was already processed.",
                ephemeral=True
            )
            return False

        return True

    # ---------------- ACCEPT ---------------- #
    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.green)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):

        if self.finished:
            return await interaction.response.send_message("Already processed.", ephemeral=True)

        guild = interaction.guild

        # ---------------- CHECK MONEY ---------------- #
        cursor.execute(
            "SELECT balance FROM money WHERE team = %s",
            (self.buyer_team,)
        )
        row = cursor.fetchone()
        buyer_balance = row[0] if row else 0

        if buyer_balance < self.amount:
            return await interaction.response.send_message(
                "❌ Not enough funds.",
                ephemeral=True
            )

        self.finished = True

        # ---------------- TRANSFER MONEY ---------------- #
        cursor.execute(
            "UPDATE money SET balance = balance - %s WHERE team = %s",
            (self.amount, self.buyer_team)
        )

        cursor.execute(
            "UPDATE money SET balance = balance + %s WHERE team = %s",
            (self.amount, self.seller_team)
        )

        conn.commit()

        # ---------------- TRANSFER PLAYER ---------------- #
for team, role_id in TEAM_ROLES.items():
    role = guild.get_role(role_id)
    if role and role.id in self.player_roles:
        await self.player.remove_roles(role)

role_id = TEAM_ROLES.get(self.buyer_team)
new_role = guild.get_role(role_id) if role_id else None

if new_role:
    await self.player.add_roles(new_role)
        # ---------------- PLAYER NOTE ---------------- #
        cursor.execute("""
            INSERT INTO player_notes (user_id, note)
            VALUES (%s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET note = EXCLUDED.note
        """, (
            self.player.id,
            f"Transferred to {self.buyer_team} for ${self.amount:,}"
        ))
        conn.commit()

        # ---------------- DM MANAGER ---------------- #
        try:
            await self.manager.send(
                f"✅ ACCEPTED\nPlayer: {self.player.display_name}\n"
                f"Team: {self.buyer_team}\n"
                f"Fee: ${self.amount:,}"
            )
        except:
            pass

        # ---------------- UPDATE MESSAGE ---------------- #
        embed = discord.Embed(
            title="✅ Negotiation Accepted",
            description=(
                f"**{self.player.display_name}** moved from **{self.seller_team}** "
                f"to **{self.buyer_team}** for **${self.amount:,}**"
            ),
            color=discord.Color.green()
        )

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)

    # ---------------- DECLINE ---------------- #
    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.red)
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):

        if self.finished:
            return await interaction.response.send_message("Already processed.", ephemeral=True)

        self.finished = True

        try:
            await self.manager.send(
                f"❌ DECLINED\nPlayer: {self.player.display_name}"
            )
        except:
            pass

        embed = discord.Embed(
            title="❌ Negotiation Declined",
            description=f"Offer for **{self.player.display_name}** was rejected.",
            color=discord.Color.red()
        )

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)


# ---------------- COMMAND ---------------- #

@bot.tree.command(name="negotiate", guild=discord.Object(id=GUILD_ID))
async def negotiate(
    interaction: discord.Interaction,
    player: discord.Member,
    amount: int,
    manager: discord.Member
):

    buyer_team = get_team_by_owner(interaction.user)

    if not buyer_team:
        return await interaction.response.send_message(
            "❌ You are not assigned to a team.",
            ephemeral=True
        )

    seller_team = None
    for role in player.roles:
        if role.id in TEAM_OWNERS:
            seller_team = TEAM_OWNERS[role.id]
            break

    if not seller_team:
        return await interaction.response.send_message(
            "❌ Player is not in a team.",
            ephemeral=True
        )

    embed = discord.Embed(
        title="EFL Negotiation Offer",
        description=(
            f"Buyer: **{buyer_team}**\n"
            f"Seller: **{seller_team}**\n"
            f"Player: **{player.display_name}**\n"
            f"Offer: **${amount:,}**"
        ),
        color=discord.Color.gold()
    )

    view = NegotiationView(
        seller_team,
        buyer_team,
        player,
        amount,
        manager
    )

    try:
        await manager.send(embed=embed, view=view)

        await interaction.response.send_message(
            "✅ Offer sent successfully.",
            ephemeral=True
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ That manager has DMs disabled.",
            ephemeral=True
        )
# ---------------- FREE AGENT ---------------- #

@bot.tree.command(name="freeagent", guild=discord.Object(id=GUILD_ID))
async def freeagent(interaction: discord.Interaction, roblox_username: str, position: str, notes: str):

    url = await roblox_headshot(roblox_username)

    embed = discord.Embed(
        title="Free Agent",
        description=f"**{roblox_username}**\nPosition: {position}\nNotes: {notes}",
        color=discord.Color.blue()
    )

    if url:
        embed.set_thumbnail(url=url)

    channel = interaction.guild.get_channel(CHANNELS["freeagency"])
    await channel.send(embed=embed)

    await interaction.response.send_message("Posted.", ephemeral=True)

# ---------------- ANNOUNCEMENT ---------------- #

@bot.tree.command(name="announcement", guild=discord.Object(id=GUILD_ID))
async def announcement(interaction: discord.Interaction, message: str):

    if not has_role(interaction.user, ROLE_PERMS["admin_ops"]):
        return await interaction.response.send_message(
            "No permission.",
            ephemeral=True
        )

    embed = discord.Embed(
        title="📢 Announcement",
        description=message,
        color=discord.Color.purple()
    )

    channel = interaction.guild.get_channel(CHANNELS["announcements"])
    await channel.send(embed=embed)

    await interaction.response.send_message(
        "Sent.",
        ephemeral=True
    )

# ---------------- RESULT ---------------- #

@bot.tree.command(name="result", guild=discord.Object(id=GUILD_ID))
async def result(
    interaction: discord.Interaction,
    team1: str,
    team2: str,
    score1: int,
    score2: int,
    status: str,
    mvp: discord.Member
):

    if not has_role(interaction.user, ROLE_PERMS["admin_ops"]):
        return await interaction.response.send_message(
            "No permission.",
            ephemeral=True
        )

    embed = discord.Embed(
        title="🏆 Match Result",
        description=f"""
**{team1} {score1}-{score2} {team2}**

Status: {status}

MVP: {mvp.mention}
""",
        color=discord.Color.orange()
    )

    channel = interaction.guild.get_channel(CHANNELS["results"])
    await channel.send(embed=embed)

    await interaction.response.send_message(
        "Result posted.",
        ephemeral=True
    )
    
# ---------------- COMMAND LOGGING ---------------- #

@bot.event
async def on_app_command_completion(
    interaction: discord.Interaction,
    command: app_commands.Command
):
    try:
        log_channel = interaction.guild.get_channel(CHANNELS["logs"])

        if not log_channel:
            return

        await log_channel.send(
            f"👤 User: {interaction.user.mention}\n"
            f"🆔 ID: {interaction.user.id}\n"
            f"⚡ Command: /{command.name}\n"
            f"🏠 Server: {interaction.guild.name}"
        )

    except Exception as e:
        print(f"Logging Error: {e}")

@bot.event
async def on_ready():
    if getattr(bot, "ready_once", False):
        return

    bot.ready_once = True

    guild = discord.Object(id=GUILD_ID)

    # clear + re-sync cleanly (prevents duplicates)
    bot.tree.clear_commands(guild=guild)
    await bot.tree.sync(guild=guild)

    print(f"Synced clean commands as {bot.user}")


bot.run(TOKEN)

