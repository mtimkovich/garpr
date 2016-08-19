import os
import sys

from mongoengine import connect

# add root directory to python path
sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/../'))

from config.config import Config
from dao import Dao

# script to create new user in db
if __name__ == "__main__":
    if len(sys.argv) < 4:
        print "incorrect number of arguments!"
        print "usage: python create_user.py username password region1 [region2] [region3]...."
        sys.exit()

    username = sys.argv[1]
    password = sys.argv[2]
    regions =  sys.argv[3:]

    config = Config()
    conn = connect(config.get_db_name())
    conn.the_database.authenticate(config.get_db_user(),
                                   config.get_db_password(),
                                   source=config.get_auth_db_name())
    dao = Dao(None)
    if dao.create_user(username, password, regions):
        print "user created:", username
