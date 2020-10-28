import asyncio
import collections
import math
import operator
import random

import discord
import inflect

from bot.classes.get_reaction import get_reaction
from bot import settings

inflector = inflect.engine()

Operator = collections.namedtuple('Operator', ['symbol', 'func'])

OPERATORS = (
    Operator('+', operator.add),
    Operator('-', operator.sub),
    Operator('*', operator.mul),
    Operator('/', operator.truediv)
)


class MultimathGame:

    precision = 2

    def __init__(
            self, *,
            color=0x000000):
        self.a = 0
        self.b = 0
        self.op = None
        self.ans = 0

        self.question_count = 0

        self.color = color

    def answer_question(self, user_answer):
        """
        Returns:
            Tuple[bool, str]: A boolean indicating whether the answer
                was correct, along with a message to edit the embed
                with.
        """
        user_answer = round(user_answer, self.precision)
        if user_answer == self.ans:
            return True, 'Correct!'
        return False, (f'{user_answer:g} was incorrect; '
                       f'the answer was {self.ans:g}!')

    def embed_begin(self, ctx, users):
        """Return an Embed to be used as the beginning of the game.

        Args:
            ctx (commands.Context): The command context.
                This is used to know who started the game.
            users (Optional[List[discord.User]]):
                A list of users to show in the beginning message.
                If None, everyone is allowed.

        Returns:
            discord.Embed

        """
        description = ['React to the emojis to answer the question!']
        if users is None:
            title = f'Multimath started by {ctx.author.name}'
            description.append('Allowed users: everyone')
        else:
            users = [u for u in users if not u.bot]
            if len(users) == 1 and users[0] == ctx.author:
                title = f'Multimath started for {users[0].name}'
                description.append(f'Allowed users: {users[0].name}')
            else:
                title = f'Multimath started by {ctx.author.name}'
                description.append(
                    'Allowed users: {}'.format(
                        inflector.join([u.name for u in users])
                    )
                )

        return discord.Embed(
            title=title,
            description='\n'.join(description),
            color=self.color
        )

    def embed_finish(self, user: discord.User):
        score = self.question_count - 1
        return discord.Embed(
            title=f'Multimath finished by {user.name}',
            description=f'Final score: {score:,}',
            color=self.color
        )

    def embed_question(self, answers: dict, time_to_answer):
        description = (f'Time to answer: {time_to_answer:,g}s\n'
                       f'What is {self.a} {self.op.symbol} {self.b}?\n')
        description += '\n'.join(
            f'{emoji}: {ans:g}' for emoji, ans in answers.items())

        return discord.Embed(
            title=f'Question {self.question_count:,}',
            description=description,
            color=self.color
        )

    def generate_values(self):
        self.question_count += 1
        self.a = random.randint(1, 10)
        self.b = random.randint(1, 10)
        self.op = random.choice(OPERATORS)
        self.ans = round(self.op.func(self.a, self.b), self.precision)
        if self.ans == int(self.ans):
            # no decimal, turn to integer
            self.ans = int(self.ans)

        return self.a, self.b, self.op, self.ans

    def generate_false_answers(self, amount: int = 1, deviation: int = 20):
        "Generate numbers close to self.ans."
        is_decimal = isinstance(self.ans, float)
        rounder = 10 ** self.precision  # Used to round off decimals

        if is_decimal and self.op.symbol == '/':
            # Decimal answer from division; reduce deviation so answers
            # are harder to figure out and also make sure that the
            # bounds match the sign of the real answer
            deviation = 1
            if self.ans <= deviation:
                if self.ans > 0:
                    middle = random.uniform(0, self.ans)
                else:
                    middle = random.uniform(deviation - self.ans, deviation)
            else:
                middle = random.uniform(0, deviation)
        else:
            middle = random.randint(0, deviation)

        lower, upper = self.ans - middle, self.ans + deviation - middle

        # Generate a range of possible answers
        possible_answers = range(
            round(lower * rounder),
            round(upper * rounder) + 1
        )

        # Check if there are enough possibilities to generate `amount` answers
        # (subtract 1 to account for the real answer always existing)
        if len(possible_answers) - 1 < amount:
            raise ValueError(
                f'Cannot generate {amount} answers when deviation of '
                f'{deviation} only allows for {len(possible_answers) - 1} '
                'invalid answers'
            )

        integers = amount // 2
        # For rounding at most half the generated numbers if the real
        # answer is an integer

        answers = {self.ans}
        while len(answers) - 1 < amount:
            n = random.randint(
                possible_answers.start,
                possible_answers.stop
            ) / rounder
            # 50% chance to round number to integer
            if not is_decimal and integers and random.randint(0, 1):
                n = round(n)
                integers -= 1

            answers.add(n)

        answers.remove(self.ans)
        return list(answers)


class BotMultimathGame:
    def __init__(self, ctx, options=['🇦', '🇧', '🇨', '🇩', '🇪']):
        self._ctx = ctx
        self._client = ctx.bot
        self.options = options

        self.game = MultimathGame(
            color=int(settings.get_setting('bot_color'), 16)
        )

    async def run(self, *, channel=None, users=None):
        """
        Args:
            channel (Optional[discord.TextChannel]):
                The channel to send the message to.
                If None, uses the channel in self._ctx.
            users (Optional[Union[True, List[discord.User]]]):
                A list of users that can participate in the game.
                If None, the author of self._ctx will be the only participant.
                If True, anyone can participate.
        """
        async def finish_and_show_score(header, last_answerer=None):
            if last_answerer is None:
                last_answerer = self._ctx.author
            embed_finish = self.game.embed_finish(last_answerer)
            embed_finish.description = '\n'.join(
                [header, embed_finish.description])
            await message.edit(embed=embed_finish)

        if users is None:
            # Allow only caller
            users = [self._ctx.author]
        elif users is True:
            # Allow all participants
            users = None
        if channel is None:
            # Assumes game to be started in the caller's channel
            channel = self._ctx.channel

        message = await channel.send(
            embed=self.game.embed_begin(self._ctx, users)
        )

        for emoji in self.options:
            await message.add_reaction(emoji)

        time_to_answer = 10
        time_intermission = 3
        reaction = user = None

        await asyncio.sleep(2)

        # Begin playing
        while True:
            # Generate question
            self.game.generate_values()
            answers = self.game.generate_false_answers(
                len(self.options) - 1)
            answers.append(self.game.ans)
            random.shuffle(answers)
            answers_dict = {
                emoji: answer for emoji, answer in zip(self.options, answers)}

            # Ask question
            embed_question = self.game.embed_question(
                answers_dict, time_to_answer)
            await message.edit(embed=embed_question)

            is_correct = False
            try:
                reaction, user = await get_reaction(
                    self._client, message,
                    self.options, users,
                    timeout=time_to_answer
                )
            except asyncio.TimeoutError:
                # Timed out!
                response = f'Too late! {time_to_answer:,g} seconds have passed!'
                await message.edit(embed=discord.Embed(
                    title=embed_question.title,
                    description=response,
                    color=self.game.color
                ))
            else:
                # Get response
                user_answer = answers_dict[reaction.emoji]
                is_correct, response = self.game.answer_question(user_answer)

                # Respond with answer
                embed_answer = discord.Embed(
                    title=embed_question.title,
                    description=response,
                    color=self.game.color
                )
                await message.edit(embed=embed_answer)

            await asyncio.sleep(time_intermission)

            if is_correct:
                # Reduce time to answer
                # NOTE: keep time_to_answer rounded to 2 places so it
                # displays nicely
                time_to_answer = round(max(3, time_to_answer - 1), 2)
                time_intermission = max(1, time_intermission - 0.15)
            else:
                response = 'Expression: {} {} {}\n{}'.format(
                    self.game.a,
                    self.game.op.symbol,
                    self.game.b,
                    response
                )
                return await finish_and_show_score(response, user)
