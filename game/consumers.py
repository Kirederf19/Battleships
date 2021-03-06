from channels.generic.websocket import WebsocketConsumer, JsonWebsocketConsumer
from django.contrib.auth.models import User
import json
from asgiref.sync import async_to_sync
from .models import Game, User
from .serializers import *
import ast

class LobbyConsumer(WebsocketConsumer):

    http_user = True
    
    def connect(self):
        self.room_name = 'lobby'
        self.room_group_name = 'game'
        
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )
        
        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name
        )

    def receive(self, text_data, **kwargs):
        channel_session_user = True
        content = ast.literal_eval(text_data)
        action = content['action']
        if action == 'create_game':
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'new_game'
                }
            )
            player = User.objects.get(username=ast.literal_eval(text_data)['player'])
            Game.create_new_game(player, 10, 10, 5)
            #delete_all_user_ships(player)
            
        if action == 'find_game':
            return Game.get_available_games()
        
        if action == 'create_board':
            Cell.create_new_board(content['game_id'], content['rows'], content['cols'], content['p1_id'], content['p2_id'])
            
        if action == 'place_ship':
            Cell.set_cell_state(content['game_id'], content['rows'], content['cols'], content['player_id'], content['new_state'])
        
        if action == 'get_ships_list':
            return Shipyard.get_all_ships()
            
        if action == 'join_game':
            player = User.objects.get(username=ast.literal_eval(text_data)['player'])
            Game.add_p2(context['game_id'], player)
            delete_all_user_ships(player)
            
        if action == 'create_user':
            User.create_new_user(content['username'])
        
        if action == 'delete_user':
            User.delete_user(content['user_id'])
        
        if action == 'add_user_ship':
            User_Shipyard.add_user_ship(content['user_id'], content['ship_id'])
        
        if action == 'get_user_shipyard_size':
            return get_user_shipyard_size(content['user_id'])
    
            User_Shipyard.add_user_ship(content['user_id'], content['ship_id'])
        
        if action == 'delete_user_ship':
            User_Shipyard.delete_user_ship(content['user_id'], content['ship_id'])
            
    def new_game(self, event):
        avail_game_list = Game.get_available_games()
        avail_serializer = GameSerializer(avail_game_list, many=True)
        self.send(text_data=json.dumps(avail_serializer.data))
        

class GameConsumer(JsonWebsocketConsumer):
    # Set to True to automatically port users from HTTP cookies
    # (you don't need channel_session_user, this implies it)
    http_user = True

    def connect(self, **kwargs):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = 'game-' + format(kwargs['game_id'])
        
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )
        
        self.accept()

    def receive(self, text_data, **kwargs):
        """
        Called when a message is received with either text or bytes
        filled out.
        """
        channel_session_user = True
        content = ast.literal_eval(text_data)
        action = content['action']
        
        if action == 'placeship':
            game_id = content['game_id']
            start_row = content['start_row']
            start_col = content['start_col']
            ship_id = content['ship_id']
            game = Game.get_game(game_id)
            ship = Shipyard.get_ship(ship_id)
            if not Game.get_both_ready(game_id):
                ship_count = User_Shipyard.get_user_shipyard_size(self.message.user)
                if ship_count < game.max_ships:
                    if not User_Shipyard.contains_user_ship(self.message.user,ship_id):
                        User_Shipyard.add_user_ship(self.message.user,ship_id)
                        for i in range(0,ship.length):
                            x = i
                            y = 0
                            if content['vertical'] == true:
                                x = 0
                                y = i
                            Cell.set_cell_state(game_id, self.message.user, 1, start_row+y, start_col+x, '{0}'.format(ship_id))
                        Game.set_ship_count(game_id,self.message.user,ship_count+1)
        
        if action == 'ready_to_start':
            set_ready(content['game_id'], self.message.user)
        
        if action == 'get_turn':
            message = {'turn': '{0}'.format(Game.get_game(content['game_id']).player_turn)}
            #Group('user-{0}'.format(self.message.user)).send({'text': json.dumps(message)})#TODO - make this like the lobby consumer
        
        if action == 'fire':
            game_id = content['game_id']
            row = content['row']
            col = content['column']
            game = Game.get_game(game_id)
            opponent_id = game.p1
            opponent_ship_count = game.p1_ship_count
            player_num = Game.get_player_num(game_id,self.message.user)
            if player_num == 1:
                opponent_id = game.p2
                opponent_ship_count = game.p2_ship_count
            if player_num != 0:
                if game.player_turn == player_num:
                    player_cell = Cell.get_cell(game_id, self.message.user, 2, row, col)
                    opponent_cell = Cell.get_cell(game_id, opponent_id, 1, row, col)
                    if player_cell.state == 'unknown':
                        opponent_cell_state = opponent_cell.state
                        if opponent_cell_state == 'sea':
                            Cell.set_cell_state(game_id, self.message.user, 2, row, col, 'miss')
                            message = {'row': row, 'col': col, 'hit_or_miss': 'miss'}
                            #Group('game-{0}'.format(game_id)).send({'text': json.dumps(message)})#TODO - make this like the lobby consumer
                        else:
                            Cell.set_cell_state(game_id, self.message.user, 2, row, col, 'hit')
                            message = {'row': row, 'col': col, 'hit_or_miss': 'hit'}
                            Group('game-{0}'.format(game_id)).send({'text': json.dumps(message)})
                            ship_id = int(opponent_cell_state)
                            User_Shipyard.inc_hit_count(opponent_id,ship_id)
                            ship_length = Shipyard.get_ship(ship_id).length
                            if ship_length == User_Shipyard.get_ship(opponent_id,ship_id).hit_count:
                                Game.set_ship_count(game_id, opponent_id, opponent_ship_count-1)
                                if opponent_ship_count == 1:
                                    Battleships_User.inc_games_played(self.message.user)
                                    Battleships_User.inc_games_played(opponent_id)
                                    Battleships_User.inc_wins(self.message.user)
                                    message = {'winner': '{0}'.format(self.message.user)}
                                    #Group('game-{0}'.format(game_id)).send({'text': json.dumps(message)})#TODO - make this like the lobby consumer
                        Cell.set_cell_state(game_id, opponent_id, 1, row, col, opponent_cell_state+'-fired_at')
                        Game.set_next_turn(game_id)

    def disconnect(self, message, **kwargs):
        """
        Perform things on connection close
        """
        pass
