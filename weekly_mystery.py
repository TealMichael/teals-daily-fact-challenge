from __future__ import annotations

"""Weekly curiosity reward for Teal's Daily Fact Challenge.

The mystery bank is intentionally local and curated so the classroom experience
never depends on a live web request.  Every school week receives one shared
mystery. Monday-Thursday completion unlocks one clue per completed day. Students may
make Guess #1 on Thursday and Guess #2 on Friday; Friday then reveals the answer.
Skipped clue days are never backfilled.
"""

from dataclasses import dataclass
from datetime import date, timedelta
import re
import unicodedata


@dataclass(frozen=True)
class MysteryDefinition:
    key: str
    category: str
    answer: str
    clues: tuple[str, str, str, str]
    reveal_note: str
    aliases: tuple[str, ...] = ()


def _m(key: str, category: str, answer: str, clues: tuple[str, str, str, str], note: str, *aliases: str) -> MysteryDefinition:
    return MysteryDefinition(key, category, answer, clues, note, tuple(aliases))


MYSTERIES: tuple[MysteryDefinition, ...] = (
    # Places
    _m("grand-canyon", "🌎 Places", "Grand Canyon", ("I am a place in the United States shaped mostly by nature.", "A river helped carve me over millions of years.", "I am in Arizona and my layered rock walls are famous around the world.", "The Colorado River runs through the bottom of me."), "Some rocks exposed in the Grand Canyon are nearly 2 billion years old.", "the grand canyon"),
    _m("mount-everest", "🌎 Places", "Mount Everest", ("I am a natural place that reaches very high above Earth.", "People travel from around the world to try to reach my top.", "I am part of the Himalayas in Asia.", "I am the highest mountain above sea level on Earth."), "Mount Everest rises along the border of Nepal and China.", "everest"),
    _m("eiffel-tower", "🌎 Places", "Eiffel Tower", ("I am a human-made landmark visited by millions of people.", "I was built in the 1800s for a major international event.", "I am made mostly of iron and stand in a European capital.", "You can find me in Paris, France."), "The Eiffel Tower was completed in 1889.", "the eiffel tower"),
    _m("great-barrier-reef", "🌎 Places", "Great Barrier Reef", ("I am a huge natural place made by living things.", "I can be seen beneath warm ocean water.", "Thousands of kinds of sea animals live around me.", "I stretch along the coast of Australia and am the world's largest coral reef system."), "The Great Barrier Reef is made up of thousands of individual reefs and islands.", "the great barrier reef"),
    _m("statue-of-liberty", "🌎 Places", "Statue of Liberty", ("I am a famous human-made landmark in the United States.", "I arrived as a gift from another country.", "I stand on an island and hold something high in one hand.", "I am the giant green statue in New York Harbor."), "France gave the Statue of Liberty to the United States.", "the statue of liberty", "lady liberty"),
    _m("antarctica", "🌎 Places", "Antarctica", ("I am a very large place where almost nobody lives permanently.", "Most of my surface is covered by ice.", "I surround the South Pole.", "I am Earth's southernmost continent."), "Antarctica holds most of Earth's freshwater ice.", "the antarctic"),
    _m("amazon-rainforest", "🌎 Places", "Amazon Rainforest", ("I am a huge natural region filled with living things.", "I receive a great deal of rain and stay warm most of the year.", "A famous river with the same name runs through me.", "Most of me lies in Brazil in South America."), "The Amazon rainforest spans several South American countries.", "the amazon rainforest", "amazon"),
    _m("hawaii", "🌎 Places", "Hawaii", ("I am part of the United States but separated from the mainland.", "Volcanoes helped create me.", "I am made of islands in the Pacific Ocean.", "Honolulu is my capital."), "Hawaii became the 50th U.S. state in 1959.", "state of hawaii"),
    _m("niagara-falls", "🌎 Places", "Niagara Falls", ("I am a natural landmark involving a lot of moving water.", "I sit along an international border in North America.", "Visitors often wear rain ponchos near me.", "I am a group of huge waterfalls between the United States and Canada."), "Niagara Falls is actually made of three waterfalls.", "the niagara falls"),
    _m("golden-gate-bridge", "🌎 Places", "Golden Gate Bridge", ("I am a famous structure that helps people cross water.", "I opened in the 1930s.", "My towers and long cables are easy to recognize.", "I am the orange-red suspension bridge beside San Francisco."), "The Golden Gate Bridge opened to traffic in 1937.", "the golden gate bridge"),

    # Animals
    _m("cheetah", "🐾 Animals", "Cheetah", ("I am a land animal and a hunter.", "My body is built for short bursts of incredible speed.", "I have dark spots and long legs.", "I am the fastest land animal."), "A cheetah can accelerate extremely quickly, but it cannot keep top speed for long."),
    _m("octopus", "🐾 Animals", "Octopus", ("I live in the ocean and have no bones.", "I am known for solving problems and escaping tight spaces.", "I can change my color and texture to hide.", "I have eight arms."), "An octopus has three hearts.", "an octopus"),
    _m("emperor-penguin", "🐾 Animals", "Emperor Penguin", ("I am a bird, but I do not fly.", "I am an excellent swimmer and live in a very cold place.", "Parents take turns protecting an egg through harsh weather.", "I am the largest penguin species and live in Antarctica."), "Male emperor penguins balance the egg on their feet during winter.", "emperor penguin", "penguin"),
    _m("blue-whale", "🐾 Animals", "Blue Whale", ("I am an animal that lives entirely in water.", "I breathe air even though I live in the ocean.", "My food can be tiny compared with my body.", "I am the largest animal known to have lived on Earth."), "A blue whale's heart can weigh hundreds of pounds.", "blue whale", "the blue whale"),
    _m("axolotl", "🐾 Animals", "Axolotl", ("I am a small animal that spends my life in water.", "I can regrow several body parts after injury.", "I often look as if I have feathery branches beside my head.", "I am a salamander originally from lakes near Mexico City."), "Axolotls can regenerate limbs and parts of some organs."),
    _m("honeybee", "🐾 Animals", "Honeybee", ("I am a small animal that lives in a large social group.", "I help many plants reproduce as I search for food.", "Workers communicate information about food through movement.", "I collect nectar and my colony makes honey."), "Honeybees use a waggle dance to communicate where food is located.", "honey bee", "bee"),
    _m("giraffe", "🐾 Animals", "Giraffe", ("I am a large plant-eating land animal.", "My patterned coat helps individuals look different from one another.", "I can reach food that many other animals cannot.", "I am famous for my extremely long neck."), "A giraffe has seven neck vertebrae, the same number as a human."),
    _m("platypus", "🐾 Animals", "Platypus", ("I am an animal native to Australia.", "I spend time in water but also move on land.", "I am a mammal that lays eggs.", "I have a broad bill and webbed feet."), "The platypus is one of the few living mammals that lays eggs.", "duck billed platypus", "duck-billed platypus"),
    _m("bald-eagle", "🐾 Animals", "Bald Eagle", ("I am a bird of prey found in North America.", "I often live near lakes, rivers, and coasts where I can find fish.", "Adults have a dark body with a bright white head.", "I am the national bird of the United States."), "Bald eagles build some of the largest nests made by birds.", "the bald eagle", "eagle"),
    _m("kangaroo", "🐾 Animals", "Kangaroo", ("I am a plant-eating animal from Australia.", "My powerful back legs help me travel in a way most mammals do not.", "A mother carries her young in a pouch.", "I move mainly by hopping."), "A baby kangaroo is called a joey."),

    # Foods
    _m("pineapple", "🍕 Foods", "Pineapple", ("I am something people eat and I grow on a plant.", "My outside is rough, but my inside is sweet and juicy.", "I have a crown of stiff green leaves.", "My name combines a tree word and a fruit word even though I grow close to the ground."), "A pineapple is formed from many small flowers whose fruits fuse together."),
    _m("popcorn", "🍕 Foods", "Popcorn", ("I begin as a small, hard food.", "Heat changes me very quickly.", "I am strongly connected with watching movies.", "I pop when water inside a corn kernel turns to steam."), "A popcorn kernel pops because pressure builds inside its tough outer shell."),
    _m("sushi", "🍕 Foods", "Sushi", ("I am a food with many different varieties.", "Rice is a key part of me.", "Some versions contain seafood, vegetables, or egg.", "I am a Japanese food often served in rolls or small bite-sized pieces."), "Sushi refers to the seasoned rice; it does not always contain raw fish."),
    _m("pizza", "🍕 Foods", "Pizza", ("I am a food that can be made in many shapes and styles.", "People often share me by cutting me into pieces.", "Cheese and tomato sauce are common on me.", "I am a baked flat dough topped before cooking."), "Pizza styles vary widely from thin crust to deep dish."),
    _m("chocolate", "🍕 Foods", "Chocolate", ("I am a food that begins with seeds from a tropical tree.", "I can taste bitter, sweet, or somewhere in between.", "I am often made into bars, drinks, and desserts.", "I come from cacao beans."), "Cacao beans grow inside large pods on cacao trees."),
    _m("avocado", "🍕 Foods", "Avocado", ("I am a fruit even though I am not usually very sweet.", "My edible inside is soft and green.", "I have one large seed in the center.", "I am the main ingredient in guacamole."), "Botanically, an avocado is a berry with one large seed."),
    _m("pretzel", "🍕 Foods", "Pretzel", ("I am a baked food made from dough.", "I can be soft or crunchy.", "My traditional shape loops and crosses over itself.", "I am often sprinkled with coarse salt."), "Pretzels have been made in Europe for many centuries."),
    _m("watermelon", "🍕 Foods", "Watermelon", ("I am a fruit with a thick outer rind.", "I am especially popular in warm weather.", "My inside is usually red or pink and contains lots of water.", "I am a large melon often associated with black seeds."), "Watermelon is more than 90 percent water."),
    _m("tacos", "🍕 Foods", "Tacos", ("I am a food that can hold many different fillings.", "I am usually eaten with your hands.", "My outer layer may be soft or crunchy and is made from a tortilla.", "I am a Mexican dish often folded around meat, beans, vegetables, or cheese."), "Tacos can be made with corn or flour tortillas and countless fillings.", "taco"),
    _m("maple-syrup", "🍕 Foods", "Maple Syrup", ("I am a sweet food that begins as liquid collected from a tree.", "Making me requires boiling away a lot of water.", "I am strongly associated with Canada and the northeastern United States.", "People often pour me on pancakes and waffles."), "It takes many gallons of maple sap to make one gallon of maple syrup.", "syrup"),

    # Sports
    _m("basketball", "🏀 Sports", "Basketball", ("I am a sport played with a ball.", "Players score at opposite ends of a court.", "Dribbling is an important way to move while playing me.", "My goal is to put the ball through a raised hoop."), "Basketball was invented by James Naismith in 1891."),
    _m("soccer", "🏀 Sports", "Soccer", ("I am a team sport played around the world.", "Most players cannot use their hands during normal play.", "A match usually has two goals, one at each end of the field.", "I am called football in much of the world."), "Soccer is one of the world's most widely played sports.", "football"),
    _m("baseball", "🏀 Sports", "Baseball", ("I am a team sport played in turns on offense and defense.", "Players move around four bases.", "A pitcher sends the ball toward a batter.", "Three strikes can make an out in my game."), "A regulation baseball field has bases arranged in a diamond."),
    _m("tennis", "🏀 Sports", "Tennis", ("I can be played one-on-one or two-on-two.", "A net divides my playing area.", "Players use stringed rackets to hit a ball.", "My scores famously use love, 15, 30, and 40."), "The word 'love' is used for a score of zero in tennis."),
    _m("indy-500", "🏀 Sports", "Indianapolis 500", ("I am a sporting event held once each year.", "Competitors travel at very high speeds.", "My race covers 500 miles.", "I take place at the Indianapolis Motor Speedway in Indiana."), "The Indianapolis 500 has been held for more than a century.", "indy 500", "the indy 500", "the indianapolis 500"),
    _m("super-bowl", "🏀 Sports", "Super Bowl", ("I am a major American sporting event held once a year.", "Millions of people watch me, including people interested in the commercials and halftime show.", "I decide the champion of a professional league.", "I am the championship game of the NFL."), "The first game later called the Super Bowl was played in 1967.", "the super bowl"),
    _m("olympic-games", "🏀 Sports", "Olympic Games", ("I bring athletes from many countries together.", "I include many different sports instead of just one.", "My symbol uses five connected rings.", "I have separate Summer and Winter versions."), "The five Olympic rings are one of the most recognized symbols in sports.", "olympics", "the olympics", "olympic games", "the olympic games"),
    _m("chicago-cubs", "🏀 Sports", "Chicago Cubs", ("I am a professional sports team in the United States.", "My sport is played with bats, gloves, and bases.", "My home ballpark is one of the oldest in my league.", "I play baseball at Wrigley Field in Chicago."), "The Cubs ended a 108-year championship drought in 2016.", "cubs", "the chicago cubs", "the cubs"),
    _m("harlem-globetrotters", "🏀 Sports", "Harlem Globetrotters", ("I am a basketball team, but entertainment is a huge part of what I do.", "My players are known for tricks, comedy, and amazing ball handling.", "I have performed in countries around the world.", "My name includes a New York neighborhood even though I travel constantly."), "The Harlem Globetrotters have entertained audiences for generations.", "the harlem globetrotters", "globetrotters"),
    _m("bowling", "🏀 Sports", "Bowling", ("I am a sport often played indoors.", "Players send an object down a long narrow lane.", "A perfect result on one turn knocks down ten targets.", "Players roll a heavy ball toward pins."), "Three strikes in a row in bowling are often called a turkey."),

    # Science & nature
    _m("saturn", "🔬 Science & Nature", "Saturn", ("I am in our solar system.", "I am much larger than Earth and mostly made of gas.", "I have many moons.", "I am famous for a spectacular system of rings."), "Saturn's rings are made mostly of countless pieces of ice and rock."),
    _m("mars", "🔬 Science & Nature", "Mars", ("I am in our solar system.", "Robotic spacecraft have explored my surface.", "Iron minerals help give me a reddish color.", "I am often called the Red Planet."), "Mars has the largest volcano known in the solar system, Olympus Mons."),
    _m("volcano", "🔬 Science & Nature", "Volcano", ("I am a natural feature connected to Earth's interior.", "I can stay quiet for a very long time and then suddenly become active.", "Melted rock may emerge from me.", "I can erupt lava, ash, and gases."), "Magma is called lava after it reaches Earth's surface."),
    _m("lightning", "🔬 Science & Nature", "Lightning", ("I am a natural event that happens very quickly.", "I am associated with storms.", "I involve a huge electrical discharge.", "You usually see me before you hear the thunder I cause."), "Light travels much faster than sound, which is why lightning is seen before thunder is heard.", "lightning bolt"),
    _m("tornado", "🔬 Science & Nature", "Tornado", ("I am a weather event that can form during powerful storms.", "I involve rapidly rotating air.", "I can create a narrow path of intense damage.", "I often appear as a funnel extending from a thunderstorm toward the ground."), "Tornado wind speeds can vary enormously from one storm to another."),
    _m("rainbow", "🔬 Science & Nature", "Rainbow", ("I am something you can sometimes see in the sky.", "Water droplets help create me.", "Light is separated into different colors when I appear.", "I often appear when sunlight shines through rain."), "A rainbow is actually a full circle, although the ground usually blocks part of it from view."),
    _m("moon", "🔬 Science & Nature", "Moon", ("I am a natural object in space.", "My appearance seems to change in a repeating pattern during each month.", "Humans first visited my surface in 1969.", "I orbit Earth."), "The same side of the Moon generally faces Earth because of synchronous rotation.", "the moon", "earth's moon", "earths moon"),
    _m("dna", "🔬 Science & Nature", "DNA", ("I am found inside living things.", "I carry instructions used by cells.", "My structure is often described as a twisted ladder.", "My famous shape is called a double helix."), "DNA stores genetic information using a sequence of four chemical bases.", "deoxyribonucleic acid"),
    _m("solar-eclipse", "🔬 Science & Nature", "Solar Eclipse", ("I am an event involving objects in space lining up.", "I can make daytime suddenly become much darker in a narrow area.", "You must use proper eye protection to watch most of me safely.", "I happen when the Moon moves between Earth and the Sun."), "A total solar eclipse is visible only from a relatively narrow path on Earth.", "eclipse", "a solar eclipse"),
    _m("coral", "🔬 Science & Nature", "Coral", ("I live in the ocean and may look like a plant or rock.", "Many of us together can create enormous habitats.", "Tiny animals called polyps build hard skeletons.", "I am the living builder of vast reef habitats."), "Coral reefs support an extraordinary variety of ocean life.", "corals"),

    # History & people
    _m("amelia-earhart", "🏛️ History & People", "Amelia Earhart", ("I became famous during the early history of aviation.", "I set records while traveling long distances.", "I was an American woman whose final flight became a mystery.", "I was the first woman to fly solo across the Atlantic Ocean."), "Amelia Earhart inspired generations of pilots and adventurers.", "earhart"),
    _m("abraham-lincoln", "🏛️ History & People", "Abraham Lincoln", ("I was an American leader in the 1800s.", "I led the country during a civil war.", "One of my most famous speeches was very short and delivered at Gettysburg.", "I was the 16th president of the United States."), "Lincoln delivered the Gettysburg Address in 1863.", "lincoln", "abe lincoln"),
    _m("rosa-parks", "🏛️ History & People", "Rosa Parks", ("I was an American civil rights activist.", "A decision I made during an ordinary trip became historically important.", "My arrest helped spark a long boycott in Montgomery, Alabama.", "I refused to give up my bus seat under segregation laws."), "The Montgomery Bus Boycott lasted more than a year.", "parks"),
    _m("neil-armstrong", "🏛️ History & People", "Neil Armstrong", ("I was an American pilot and astronaut.", "I traveled farther from Earth than most people ever have.", "I took part in the Apollo 11 mission.", "I became the first person to walk on the Moon."), "Neil Armstrong stepped onto the Moon in July 1969.", "armstrong"),
    _m("thomas-edison", "🏛️ History & People", "Thomas Edison", ("I was an American inventor and businessman.", "I worked on many different technologies instead of just one invention.", "My laboratory helped develop practical electric-light systems.", "I am strongly associated with the practical incandescent light bulb and the phonograph."), "Edison held more than a thousand U.S. patents.", "edison"),
    _m("marie-curie", "🏛️ History & People", "Marie Curie", ("I was a scientist born in Poland who worked in France.", "My research changed how scientists understood certain energetic materials.", "I won Nobel Prizes in two different sciences.", "I pioneered research on radioactivity."), "Marie Curie won Nobel Prizes in both Physics and Chemistry.", "curie"),
    _m("martin-luther-king-jr", "🏛️ History & People", "Martin Luther King Jr.", ("I was an American civil rights leader.", "I promoted nonviolent protest.", "I gave a famous speech during the March on Washington in 1963.", "My 'I Have a Dream' speech is one of the best-known speeches in U.S. history."), "Martin Luther King Jr. received the Nobel Peace Prize in 1964.", "martin luther king", "mlk", "dr king", "dr martin luther king jr"),
    _m("wright-brothers", "🏛️ History & People", "Wright Brothers", ("We were two American brothers interested in machines and flight.", "We experimented with gliders before our most famous success.", "Our names were Orville and Wilbur.", "We made the first successful powered, controlled airplane flight in 1903."), "The Wright brothers' famous 1903 flights took place near Kitty Hawk, North Carolina.", "the wright brothers", "orville and wilbur wright"),
    _m("george-washington", "🏛️ History & People", "George Washington", ("I was an important American leader in the 1700s.", "I commanded the Continental Army during the Revolutionary War.", "A U.S. state and the nation's capital both use my last name.", "I was the first president of the United States."), "George Washington served two presidential terms.", "washington"),
    _m("sacagawea", "🏛️ History & People", "Sacagawea", ("I lived in North America in the early 1800s.", "I traveled thousands of miles while still a teenager.", "My language skills and knowledge helped a famous exploration expedition.", "I traveled with Lewis and Clark toward the Pacific Ocean."), "Sacagawea traveled with her infant son during much of the Lewis and Clark expedition."),

    # Music & entertainment
    _m("taylor-swift", "🎵 Music & Entertainment", "Taylor Swift", ("I am an American musician and songwriter.", "My career has included music in several styles.", "I have rerecorded several of my earlier albums.", "My concert tour called The Eras Tour became famous around the world."), "Taylor Swift began releasing music professionally as a teenager.", "swift"),
    _m("beatles", "🎵 Music & Entertainment", "The Beatles", ("We were a music group that became famous in the 1960s.", "We came from Liverpool, England.", "Our members included John, Paul, George, and Ringo.", "Songs such as 'Hey Jude' and 'Yellow Submarine' are associated with us."), "The Beatles became one of the most influential popular-music groups in history.", "beatles"),
    _m("michael-jackson", "🎵 Music & Entertainment", "Michael Jackson", ("I was an American singer and performer.", "I began performing professionally as a child with members of my family.", "A backward-gliding dance move became strongly associated with me.", "My albums include Thriller and Bad."), "Thriller became one of the best-selling albums ever.", "jackson"),
    _m("beyonce", "🎵 Music & Entertainment", "Beyoncé", ("I am an American singer and performer.", "I first became widely known as part of a music group.", "That group was called Destiny's Child.", "My solo songs include 'Crazy in Love' and 'Single Ladies.'"), "Beyoncé has performed as both a group member and a solo artist for decades.", "beyonce knowles", "beyoncé knowles"),
    _m("elvis-presley", "🎵 Music & Entertainment", "Elvis Presley", ("I was an American singer and actor.", "I became a huge star during the 1950s.", "Graceland in Memphis is strongly connected with me.", "I became known as the 'King of Rock and Roll.'"), "Elvis Presley recorded music in rock, country, blues, and gospel styles.", "elvis", "the king"),
    _m("dolly-parton", "🎵 Music & Entertainment", "Dolly Parton", ("I am an American singer, songwriter, and actor.", "I grew up in Tennessee and became famous in country music.", "I helped create a program that gives free books to young children.", "My songs include 'Jolene' and '9 to 5.'"), "Dolly Parton's Imagination Library has mailed books to millions of children.", "dolly"),
    _m("walt-disney", "🎵 Music & Entertainment", "Walt Disney", ("I was an American producer and entrepreneur.", "Animation played a huge role in my career.", "A famous mouse helped my company become known around the world.", "Theme parks in California and Florida grew from ideas connected with my name."), "Walt Disney co-founded the company that became The Walt Disney Company.", "disney"),
    _m("wizard-of-oz", "🎵 Music & Entertainment", "The Wizard of Oz", ("I am a famous story that has appeared in books and movies.", "A journey along a special road is central to me.", "A scarecrow, tin man, and lion travel together.", "Dorothy follows the yellow brick road toward the Emerald City."), "The 1939 film was based on L. Frank Baum's earlier book.", "wizard of oz"),
    _m("star-wars", "🎵 Music & Entertainment", "Star Wars", ("I am a fictional story universe that began as a movie.", "Much of my action happens far from Earth.", "Droids, spaceships, and a mysterious Force are important in my stories.", "Characters such as Luke Skywalker, Darth Vader, and Yoda are part of me."), "The first Star Wars film was released in 1977."),
    _m("minecraft", "🎵 Music & Entertainment", "Minecraft", ("I am a video game with a world made mostly from blocks.", "Players can gather resources and build almost anything they imagine.", "Creepers are one of my best-known creatures.", "My two famous basic modes include Survival and Creative."), "Minecraft worlds are procedurally generated and can be enormous."),

    # Games, toys & objects
    _m("lego", "🎲 Games, Toys & Objects", "LEGO", ("I am a toy system used to build things.", "My pieces can be taken apart and reused again and again.", "Small bumps on top help my pieces connect.", "I am famous for colorful interlocking plastic bricks."), "The name LEGO comes from Danish words meaning 'play well.'", "legos", "lego bricks"),
    _m("rubiks-cube", "🎲 Games, Toys & Objects", "Rubik's Cube", ("I am a handheld puzzle.", "I can be twisted in several directions.", "My classic version has six colored faces.", "The goal is to return each side of my 3-by-3 cube to one color."), "The Rubik's Cube was invented by Ernő Rubik in the 1970s.", "rubik cube", "rubiks cube", "the rubik's cube"),
    _m("yoyo", "🎲 Games, Toys & Objects", "Yo-Yo", ("I am a toy that moves up and down.", "I use a string wrapped around an axle.", "Skilled players perform tricks with me.", "I return toward your hand after spinning at the end of my string."), "Yo-yos have existed in different forms for centuries.", "yo yo", "yo-yo"),
    _m("monopoly", "🎲 Games, Toys & Objects", "Monopoly", ("I am a board game involving money and property.", "Players move around a square board.", "Railroads and named streets can be purchased.", "One of my spaces tells players to Go to Jail."), "Many special editions of Monopoly use different themes and locations."),
    _m("chess", "🎲 Games, Toys & Objects", "Chess", ("I am a strategy game for two players.", "My pieces move in different ways.", "Knights make an unusual L-shaped move.", "The goal is to checkmate the opponent's king."), "A chessboard has 64 squares."),
    _m("frisbee", "🎲 Games, Toys & Objects", "Frisbee", ("I am an object usually used outdoors for fun or sport.", "I travel through the air with a spinning motion.", "People often throw me back and forth.", "I am a flat flying disc."), "Flying discs can curve in flight depending on spin and release angle.", "flying disc", "disc"),
    _m("bicycle", "🎲 Games, Toys & Objects", "Bicycle", ("I help a person travel without using an engine.", "A rider usually powers me with pedals.", "A chain transfers motion to one of my wheels.", "My name hints that I normally have two wheels."), "Modern bicycles developed from several earlier two-wheeled designs.", "bike"),
    _m("telescope", "🎲 Games, Toys & Objects", "Telescope", ("I am a tool that helps people observe things that are far away.", "Scientists use versions of me on Earth and in space.", "Lenses or mirrors can collect light for me.", "Astronomers use me to study stars, planets, and galaxies."), "Some telescopes observe kinds of light that human eyes cannot see."),
    _m("compass", "🎲 Games, Toys & Objects", "Compass", ("I am a small tool used for finding direction.", "I can work without a battery.", "One part of me responds to Earth's magnetic field.", "My needle points toward magnetic north."), "A magnetic compass helps travelers identify cardinal directions."),
    _m("piano", "🎲 Games, Toys & Objects", "Piano", ("I am a musical instrument.", "A player uses both hands and may also use foot pedals.", "My standard keyboard has black and white keys.", "Pressing my keys causes hammers inside to strike strings."), "A standard modern piano keyboard usually has 88 keys."),
)

MYSTERY_BY_KEY = {item.key: item for item in MYSTERIES}


def week_start_for(day: date) -> date:
    return day - timedelta(days=day.weekday())


def school_day_number(day: date) -> int | None:
    return day.weekday() + 1 if day.weekday() < 5 else None


def normalize_guess(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text.startswith("the "):
        text = text[4:]
    return text


def is_correct_guess(mystery: MysteryDefinition, guess: str) -> bool:
    normalized = normalize_guess(guess)
    if not normalized:
        return False
    accepted = {normalize_guess(mystery.answer), *(normalize_guess(alias) for alias in mystery.aliases)}
    return normalized in accepted


def default_mystery_key_for_week(week_start: date) -> str:
    # A full-cycle stride gives every bank item a turn before the sequence
    # repeats, while still making the weekly choice deterministic for every
    # class/device. 37 is coprime with the 80-item bank.
    epoch = date(2026, 1, 5)  # Monday
    week_index = (week_start - epoch).days // 7
    index = (23 + week_index * 37) % len(MYSTERIES)
    return MYSTERIES[index].key


def next_mystery_key(current_key: str, *, offset: int = 1) -> str:
    keys = [item.key for item in MYSTERIES]
    try:
        index = keys.index(current_key)
    except ValueError:
        index = -1
    return keys[(index + int(offset)) % len(keys)]


def mystery_for_key(key: str) -> MysteryDefinition:
    try:
        return MYSTERY_BY_KEY[str(key)]
    except KeyError as exc:
        raise KeyError(f"Unknown weekly mystery key: {key}") from exc


def mystery_bank_summary() -> dict[str, int]:
    result: dict[str, int] = {}
    for item in MYSTERIES:
        result[item.category] = result.get(item.category, 0) + 1
    return result
