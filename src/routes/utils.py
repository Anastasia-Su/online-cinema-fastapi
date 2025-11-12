from enum import Enum


class SortBy(str, Enum):
    PRICE = "price"
    YEAR = "year"
    IMDB = "imdb"
    VOTES = "votes"
    TIME = "time"

class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"