import utilities, myanimelistAPI, jikan4pyAPI
import requests as r
import datetime as dt
from utilities import print_bot

malID_to_aniListID = {}
mal_api = myanimelistAPI.MyAnimeListAPI(open("secret_keys/mal.key").read())
jikan_api = jikan4pyAPI.JikanAPI()

def malIDtoAniListID(anime_id):
	"""
	Converts the MAL ID to AniList ID
	using GraphQL
	"""
	if anime_id in malID_to_aniListID:
		return malID_to_aniListID[anime_id]

	query = """query
		($id: Int, $type: MediaType) {
			Media(idMal: $id, type: $type) {
				id}
			}
		"""
	variables = {'id': anime_id, 'type': 'ANIME'}
	url = 'https://graphql.anilist.co'
	response = r.post(url, json={'query': query, 'variables': variables})
	malID_to_aniListID[anime_id] = int(response.json()['data']['Media']['id'])
	return malID_to_aniListID[anime_id]

def timeTillNextEpisode(anime_id):
	"""
	Returns the time till the next episode of the anime airs
	"""
	query = """query ($id: Int) {
					Media(idMal: $id, type: ANIME) {
						id
						nextAiringEpisode {
						timeUntilAiring
						}
					}
				}
	"""
	variables = {'id': anime_id, 'type': 'ANIME'}
	url = 'https://graphql.anilist.co'
	data = r.post(url, json={'query': query, 'variables': variables}).json()

	try: # if parsing fails, then the anime is not airing
		time_data = data['data']['Media']['nextAiringEpisode']
	except:
		time_data = None

	if time_data is not None:
		seconds = time_data['timeUntilAiring']
	else:
		return {"days": 0,
				"hours": 0,
				"minutes": 0,
				"seconds": 0,
				"total_seconds": 0,
				"isNull": True}

	time = dt.timedelta(seconds=seconds)
	return {"days": time.days,
			"hours": time.seconds//3600,
			"minutes": (time.seconds//60) % 60,
			"seconds": time.seconds % 60,
			"total_seconds": seconds,
			"isNull": False}
 
def isAnimeAiring(anime_id, api="mal"):
	"""
	Checks if the anime is airing
	using the MyAnimeList API (atleast more updated then the Jikan API due to less caching)
	"""
	if api == "mal":
		try:
			result = mal_api.getAnimeByID(anime_id)
			return (result['status'] != "finished_airing")
		except Exception as e:
			print_bot(
				f"Error: Mal API ID check failed, so switching to Jikan API.\n'{e}'")
			result = jikan_api.getAnimeByID(anime_id)
			return result["status"] != "Finished Airing"
	else:
		result = jikan_api.getAnimeByID(anime_id)
		return result["status"] != "Finished Airing"

#---------------------------------------------------------------------------
#-------------------------HERE BEGINS THE BOT-------------------------------
#---------------------------------------------------------------------------


import logging, pickledb
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import filters, ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, ConversationHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TITLE, END = range(2)
DB = pickledb.load("database.json", True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Please send me an anime name and i'll tell you when the next episode will go on air!")
    
    
async def get_anime_name(update: Update, context: ContextTypes.DEFAULT_TYPE):

	animes = jikan_api.searchAnime(anime_name=update.message.text)
	keyboard = [[anime["title"]] for anime in animes]
	keyboard.append(["Cancel"])

	reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

	await update.message.reply_text("Please select a title from the list: ", reply_markup=reply_markup)
 
	return TITLE


async def get_airing_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    airtime = timeTillNextEpisode(jikan_api.getAnimeIDByName(update.message.text))
    
    formatted = f"The next episode will be in \n{airtime['days']} days \n{airtime['hours']} hours \n{airtime['minutes']} minutes" \
        if not airtime['isNull'] else "Couldn't find the selected anime in this current season."
    
    await context.bot.send_message(chat_id=update.effective_chat.id, text=formatted, reply_markup=ReplyKeyboardRemove())
    
    return ConversationHandler.END


async def add_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE):

	if DB.get(f"{update.effective_chat.id}"):
		DB.get(f"{update.effective_chat.id}").update({jikan_api.getAnimeIDByName(update.message.text): update.message.text})
	
	else:
		DB.set(f"{update.effective_chat.id}", {jikan_api.getAnimeIDByName(update.message.text): update.message.text})
  
	DB.dump()
    
	return ConversationHandler.END


async def get_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
	if DB.get(f"{update.effective_chat.id}"):
     
		dbel = DB.get(f"{update.effective_chat.id}")
		airingtimename = []
  
		for el in dbel:
			airtime = timeTillNextEpisode(el)
			formatted_airtime = f"{airtime['days']} dd  {airtime['hours']} hh  {airtime['minutes']} mm"
			airingtimename.append(f"{dbel[el]}\n{formatted_airtime}")
  
		await context.bot.send_message(chat_id=update.effective_chat.id, text=["\n\n".join(value for value in airingtimename)][0])

	else:
		await context.bot.send_message(chat_id=update.effective_chat.id, text="Add an anime first!")
  
  
async def get_added_name(update: Update, context: ContextTypes.DEFAULT_TYPE):

	keyboard = [[value] for value in DB.get(f"{update.effective_chat.id}").values()]
	keyboard.append(["Cancel"])

	reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

	await update.message.reply_text("Please select a title from the list: ", reply_markup=reply_markup)
 
	return TITLE
  
  
async def remove_from_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
	DB.load("database.json", True)
	DB.get(f"{update.effective_chat.id}").pop(str(jikan_api.getAnimeIDByName(update.message.text)))
	DB.dump()
    
	return ConversationHandler.END

    
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Operation cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

if __name__ == '__main__':
    application = ApplicationBuilder().token(open("secret_keys/telegram.key").read()).build()
    
    start_handler = CommandHandler('start', start)
    
    airtime_handler = ConversationHandler(
		entry_points=[CommandHandler("nextep", get_anime_name)],
		states = {
			TITLE: [
				MessageHandler(filters.TEXT & (~filters.Regex(r"\bCancel\b")), callback=get_airing_time)
			]
		},
		fallbacks=[MessageHandler(filters.TEXT, done)]
	)
    
    addtolist_handler = ConversationHandler(
		entry_points=[CommandHandler("add", get_anime_name)],
		states = {
			TITLE: [
				MessageHandler(filters.TEXT & (~filters.Regex(r"\bCancel\b")), callback=add_to_list)
			]
		},
		fallbacks=[MessageHandler(filters.TEXT, done)]
	)
    
    removefromlist_handler = ConversationHandler(
		entry_points=[CommandHandler("rem", get_added_name)],
		states = {
			TITLE: [
				MessageHandler(filters.TEXT & (~filters.Regex(r"\bCancel\b")), callback=remove_from_list)
			]
		},
		fallbacks=[MessageHandler(filters.TEXT, done)]
	)
    
    getlist_handler = CommandHandler("get", get_list)
    
    application.add_handler(start_handler)
    application.add_handler(airtime_handler)
    application.add_handler(addtolist_handler)
    application.add_handler(getlist_handler)
    application.add_handler(removefromlist_handler)

    
    application.run_polling()
    