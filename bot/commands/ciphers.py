import itertools
import string

from discord.ext import commands

from bot import utils

CIPHER_ATBASH_TABLE = str.maketrans(
    string.ascii_letters,
    string.ascii_lowercase[::-1] + string.ascii_uppercase[::-1])
CIPHER_OTP_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
MORSECODE_DICTIONARY_STRING = """\
Source: https://morsecode.world/international/morse.html
"a" : .-
"b" : -...
"c" : -.-.
"d" : -..
"e" : .
"f" : ..-.
"g" : --.
"h" : ....
"i" : ..
"j" : .---
"k" : -.-
"l" : .-..
"m" : --
"n" : -.
"o" : ---
"p" : .--.
"q" : --.-
"r" : .-.
"s" : ...
"t" : -
"u" : ..-
"v" : ...-
"w" : .--
"x" : -..-
"y" : -.--
"z" : --..
"0" : -----
"1" : .----
"2" : ..---
"3" : ...--
"4" : ....-
"5" : .....
"6" : -....
"7" : --...
"8" : ---..
"9" : ----.
"," : --..--
";" : -.-.-.
"." : .-.-.-
":" : ---...
"?" : ..--..
"!" : -.-.--
"(" : -.--.
")" : -.--.-
"+" : .-.-.
"-" : -....-
"/" : -..-.
"=" : -...-
"@" : .--.-.
"&" : .-...
"_" : ..--.-
"'" : .----.
'"' : .-..-.
<new line> : .-.-
"<AA>": .-.-        New line ("\\n")
"<AR>": .-.-.       End of message ("+")
"<AS>": .-...       Wait ("&")
"<BK>": -...-.-     Break
"<BT>": -...-       New paragraph ("=")
"<CL>": -.-..-..    Going off the air (clear)
"<CT>": -.-.-       Start copying
"<DO>": -..---      Change to wabun code
"<KN>": -.--.       Invite specific station ("(")
"<SK>": ...-.-      End of transmission
"<SN>": ...-.       Understood (can also be read as <VE>)
"<SOS>": ...---...  Distress message"""
MORSECODE_DICTIONARY = {
    ':': '---...',
    ',': '--..--',
    ')': '-.--.-',
    '!': '-.-.--',
    ';': '-.-.-.',
    '-': '-....-',
    "'": '.----.',
    '@': '.--.-.',
    '.': '.-.-.-',
    '"': '.-..-.',
    '_': '..--.-',
    '?': '..--..',
    '(': '-.--.',
    '/': '-..-.',
    '=': '-...-',
    '+': '.-.-.',
    '&': '.-...',
    '0': '-----',
    '9': '----.',
    '8': '---..',
    '7': '--...',
    '6': '-....',
    '1': '.----',
    '2': '..---',
    '3': '...--',
    '4': '....-',
    '5': '.....',
    'q': '--.-',
    'z': '--..',
    'y': '-.--',
    'c': '-.-.',
    'x': '-..-',
    'b': '-...',
    'j': '.---',
    'p': '.--.',
    '\n': '.-.-',
    'l': '.-..',
    'f': '..-.',
    'v': '...-',
    'h': '....',
    'o': '---',
    'g': '--.',
    'k': '-.-',
    'd': '-..',
    'w': '.--',
    'r': '.-.',
    'u': '..-',
    's': '...',
    'm': '--',
    'n': '-.',
    'a': '.-',
    'i': '..',
    't': '-',
    'e': '.',
}
MORSECODE_DICTIONARY_INVERTED = {v: k for k, v in MORSECODE_DICTIONARY.items()}

MORSECODE_PLACEHOLDERS = str.maketrans({'.': '●', '-': '━'})
MORSECODE_PLACEHOLDERS_INVERTED = str.maketrans(
    {v: k for k, v in MORSECODE_PLACEHOLDERS.items()}
)
MORSECODE_PROSIGNS = {
    '<SOS>': '●●●━━━●●●',
    '<CL>': '━●━●●━●●',
    '<BK>': '━●●●━●━',
    '<DO>': '━●●━━━',
    '<SK>': '●●●━●━',
    '<CT>': '━●━●━',
    '<VE>': '●●●━●',
    '<SN>': '●●●━●',
}
MORSECODE_PROSIGNS_INVERTED = {
    v.translate(MORSECODE_PLACEHOLDERS_INVERTED): k
    for k, v in MORSECODE_PROSIGNS.items()
}
MORSECODE_PROSIGNS_ENCODE_ONLY = {
    '<KN>': '━●━━●',
    '<BT>': '━●●●━',
    '<AR>': '●━●━●',
    '<AS>': '●━●●●',
    '<AA>': '●━●━',
}


class Ciphers(commands.Cog):
    qualified_name = 'Ciphers'
    description = 'Commands for encoding/decoding text.'

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def ciphercaesar(shift: int, text: str):
        # a = ord('a')  # Ordinal of 'a' to allow letters to loop

        # return ''.join(
        #     chr((ord(c) - a + shift) % 26 + a)  # Shift char by shift
        #     if 'a' <= c <= 'z'  # Shift char only if a lowercase letter
        #     else c  # If not lowercase letter, do not shift it
        #     for c in string.lower()
        #     )
        alphabet = string.ascii_lowercase

        ciphertext = []
        for char in text:
            # Store uppercase for when shifting char
            uppercase = char.isupper()

            char = char.lower()

            if char in alphabet:
                # Shift char
                char = alphabet[(ord(char) - 97 + shift) % 26]
                if uppercase:
                    char = char.upper()

                ciphertext.append(char)
            else:
                # Pass-through char
                ciphertext.append(char)

        return ''.join(ciphertext)


    @commands.command(
        name='caesarcipher',
        brief='The Caesar Cipher.',
        aliases=('ciphercaesar', 'caesarcode', 'caesarshift'))
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def client_ciphercaesar(self, ctx, shift: int, *, string: str):
        """Takes an amount of letters to shift and a string.
shift: An integer amount of letters to shift. Can be a negative integer.
string: A string to cipher."""
        await ctx.send(self.ciphercaesar(shift, string))





    @staticmethod
    def cipheratbash(string: str):
        return string.translate(CIPHER_ATBASH_TABLE)


    @commands.command(
        name='atbashcipher',
        brief='The Atbash Cipher.',
        aliases=('atbcipher', 'atbc', 'atbash'))
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def client_atbash(self, ctx, *, string: str):
        """Takes a string and maps each letter to the reverse alphabet."""
        await ctx.send(self.cipheratbash(string))





    @commands.command(
        name='reversecipher',
        brief='The Reverse Cipher.',
        aliases=('reverse',))
    async def client_cipherreverse(self, ctx, *, string: str):
        """Takes a string and reverses it.
string: A string to cipher."""
        result = string[::-1]

        await ctx.send(result)





    @staticmethod
    def ciphercolumnar(key: int, s: str):
        """devwizard's version:
out = "".join([
    s[key*y + x]
    for x in range(key)
    for y in range((len(s) + key - 1) // key)
    if key*y + x < len(s)
])
thegamecracks's version:
result = []
width = (len(string) + key - 1) // key

for x in range(key):
    for y in range(width):
        numericCoordinate = y*key + x
        if numericCoordinate < len(string):
            result.append(string[numericCoordinate])"""
        return "".join([
            s[key*y + x]
            for x in range(key)
            for y in range((len(s) + key - 1) // key)
            if key*y + x < len(s)
        ])


    @commands.command(
        name='columnarcipher',
        brief='The Columnar Transposition Cipher.',
        aliases=('transcipher', 'tpcipher'))
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def client_ciphercolumnar(self, ctx, key: int, *, string: str):
        """See http://inventwithpython.com/cracking/chapter7.html
key: The integer key to use in the cipher.
 Must be between 2 and half the message size.
string: A string to cipher.

1. Count the number of characters in the message.
2. Draw a row of a number of boxes equal to the key (for example, 8 boxes
for a key of 8).
3. Start filling in the boxes from left to right, entering
one character per box.
4. When you run out of boxes but still have more characters,
add another row of boxes.
5. When you reach the last character, shade in the unused boxes
in the last row.
6. Starting from the top left and going down each column,
write out the characters. When you get to the bottom of a column,
move to the next column to the right. Skip any shaded boxes.
This will be the ciphertext."""
        # Test if key is in valid range
        if key < 2 or key > len(string) // 2:
            return await ctx.send('Key is out of range.')

        await ctx.send(self.ciphercolumnar(key, string))





    @staticmethod
    def cipherotp(text: str, key: str, decipher: bool):
        text = text.upper()
        key = key.upper()
        cipher_otp_chars_length = len(CIPHER_OTP_CHARS)
        char_map = tuple(zip(text, key))

        for char, key_char in char_map:
            if char not in CIPHER_OTP_CHARS:
                raise ValueError(
                    f'Invalid character {char!r} given; '
                    'must be an alphanumeric character')
            if key_char not in CIPHER_OTP_CHARS:
                raise ValueError(
                    f'Invalid key character {key_char!r} given; '
                    'must be an alphanumeric character')

        if decipher:
            return ''.join([
                CIPHER_OTP_CHARS[
                    (CIPHER_OTP_CHARS.index(char)
                     - CIPHER_OTP_CHARS.index(key_char)
                     ) % cipher_otp_chars_length]
                for char, key_char in char_map])
        else:
            return ''.join([
                CIPHER_OTP_CHARS[
                    (CIPHER_OTP_CHARS.index(char)
                     + CIPHER_OTP_CHARS.index(key_char)
                     ) % cipher_otp_chars_length]
                for char, key_char in char_map])


    @commands.command(
        name='otpcipher',
        brief='The One-time Pad Cipher.',
        aliases=('otpc',))
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def client_cipherotp(self, ctx, mode: str, text: str, key: str):
        """Cipher/decipher alphanumeric text (excluding spaces) \
using the one-time pad cipher.
mode: Indicate whether to cipher or decipher the text
 ("cipher"/"ci", "decipher"/"de").
text: The text to cipher/decipher.
key: The one time key to use."""
        mode = mode.casefold()

        if mode in ('cipher', 'ci'):
            mode = False
        elif mode in ('decipher', 'de'):
            mode = True
        else:
            return await ctx.send('Mode must be either "cipher" or "decipher"')

        await ctx.send(self.cipherotp(text, key, mode))





    @staticmethod
    def morsecode(decoding, s, character_gap=' ', space_char=' / '):
        """Converts between alphanumeric characters and morse code.

        `character_gap` always decodes to nothing,
        and `space_char` always decodes to a space.

        Args:
            decoding (bool): Decodes the message.
            s (str): The message to encode or decode.
            character_gap (str): The string that represents the pause
                between characters in morse code.
            space_char (str): The string that represents the space character.

        Returns:
            str

        """
        def encode_prosigns(word):
            def _replace():
                nonlocal word
                i = word.find(k)
                while i != -1:
                    new = [word[:i]]
                    if i != 0:
                        new.append(character_gap)
                    new.append(v)
                    new.append(word[i + len(k):])
                    word = ''.join(new)
                    i = word.find(k)

            for k, v in MORSECODE_PROSIGNS.items():
                _replace()
            for k, v in MORSECODE_PROSIGNS_ENCODE_ONLY.items():
                _replace()
            return word

        def encode_word(word):
            word = encode_prosigns(word)
            word = [MORSECODE_DICTIONARY.get(c, c) for c in word]
            for i, c in enumerate(word):
                if c not in ('●', '━') and c != character_gap and i != 0:
                    word[i] = '{}{}'.format(character_gap, c)
            return ''.join(word)

        if not s:
            return ''

        newline_encoding = MORSECODE_DICTIONARY['\n']

        # Replace unicode dots and dashes with ascii versions,
        # allowing the user to decode unicode strings
        s = s.translate(MORSECODE_PLACEHOLDERS_INVERTED)

        if decoding:
            s = s.split(space_char)
            for i, word in enumerate(s):
                prosign = MORSECODE_PROSIGNS_INVERTED.get(word)
                if prosign is not None:
                    s[i] = prosign
                else:
                    decode = []
                    for c in word.split(character_gap):
                        decode_char = MORSECODE_DICTIONARY_INVERTED.get(c)
                        if decode_char is not None:
                            decode.append(decode_char)
                        else:
                            decode.append(
                                MORSECODE_PROSIGNS_INVERTED.get(c, c)
                            )
                    s[i] = ''.join(decode)
            return ' '.join(s).upper()
        else:
            s = s.lower().split(' ')
            for i, word in enumerate(s):
                prosign = MORSECODE_PROSIGNS.get(word)
                if prosign is None:
                    prosign = MORSECODE_PROSIGNS_ENCODE_ONLY.get(word)

                if prosign is not None:
                    s[i] = prosign.translate(MORSECODE_PLACEHOLDERS_INVERTED)
                elif '\n' in word:
                    # Break up the word and encode the newline
                    left, right = word.split('\n', 1)

                    s[i] = '{}{gap}{}{gap}{}'.format(
                        encode_word(left),
                        newline_encoding,
                        encode_word(right),
                        gap=character_gap
                    )
                else:
                    word = encode_word(word)
                    s[i] = word.translate(MORSECODE_PLACEHOLDERS_INVERTED)
            return space_char.join(s)


    @commands.command(
        name='morsecode',
        brief='The morse code encrypter/decrypter.',
        aliases=('morse', 'mc', 'mcode'))
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def client_morsecode(self, ctx,
        mode: str, spacing: str, *, string: str):
        """Translates text to morse code and back.
mode: Either "encode"/"en" or "decode"/"de". Selects between encoding and decoding.
spacing: Either "space"/"spaces" or "bar"/"bars". Selects between using " "/" / " and "|"/"||" to show letter and word gaps.
string: The text or morse code to encrypt/decrypt.
Allowed characters:
    abcdefghijklmnopqrstuvwxyz 0123456789,;.:?!()+-/=@&_'"
Prosigns that are encoded and decoded cleanly:
    <BK>  Break
    <CL>  Going off the air ("clear")
    <CT>  Start copying
    <DO>  Change to wabun code
    <SK>  End of transmission
    <SOS> Distress message
Prosigns that are decoded differently:
    <AA>  New line                -> an actual new line
    <AR>  End of message          -> +
    <AS>  Wait                    -> &
    <BT>  New paragraph           -> =
    <KN>  Invite specific station -> (
    <SN>  Understood (alternate form <VE> can be used, but decodes to <SN>)
Other characters will be passed through."""
        mode = mode.casefold()
        spacing = spacing.casefold()

        if mode in ('encode', 'en'):
            decoding = False
        elif mode in ('decode', 'de'):
            decoding = True
        else:
            raise ValueError(f'Unknown mode {mode!r}')

        if spacing in ('space', 'spaces'):
            character_gap = ' '
            space_char = ' / '
        elif spacing in ('bar', 'bars'):
            character_gap = '|'
            space_char = '||'
        else:
            raise ValueError(f'Unknown spacing {spacing!r}')

        message = self.morsecode(
            decoding, string,
            character_gap, space_char
        )

        await ctx.send(f'```\n{message}```')


    @client_morsecode.error
    async def client_morsecode_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, ValueError):
            await ctx.send(str(error))


    @commands.command(
        name='morsecodetable',
        brief='The interational morse code table.',
        aliases=('mcodetable', 'mct', 'morsetable'))
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def client_morsecodetable(self, ctx):
        """DMs the interational morse code table."""
        await ctx.author.send('```' + MORSECODE_DICTIONARY_STRING + '```')





    @staticmethod
    def ciphervigenere(text: str, key: str, decipher: bool):
        alphabet = string.ascii_lowercase
        decipher = int(decipher)

        # Convert key into numbers in an endless generator
        key = itertools.cycle([ord(c) - 97 for c in key.lower()])

        text_cipher = []
        for char in text:
            # Store uppercase for when shifting char
            uppercase = char.isupper()

            char = char.lower()

            if char in alphabet:
                # Shift char
                shift = -next(key) if decipher else next(key)
                char = alphabet[(ord(char) - 97 + shift) % 26]
                if uppercase:
                    char = char.upper()

                text_cipher.append(char)
            else:
                # Pass-through char
                text_cipher.append(char)

        return ''.join(text_cipher)


    @commands.command(
        name='vigenerecipher',
        brief='The Vigenere Cipher.')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def client_vigenerecipher(self, ctx,
        mode: str, key: str, *, text: str):
        """Encrypt.
mode: Either "encrypt"/"en" or "decrypt"/"de". Selects between encrypting and decrypting.
key: The key to use.
text: The text to encrypt/decrypt."""
        mode = mode.casefold()

        if mode in ('encrypt', 'en'):
            decrypting = False
        elif mode in ('decrypt', 'de'):
            decrypting = True
        else:
            raise ValueError(f'Unknown mode {mode!r}')

        await ctx.send(
            '```' + self.ciphervigenere(text, key, decrypting) + '```')


    @client_vigenerecipher.error
    async def client_vigenerecipher_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, ValueError):
            await ctx.send(str(error))










def setup(bot):
    bot.add_cog(Ciphers(bot))
