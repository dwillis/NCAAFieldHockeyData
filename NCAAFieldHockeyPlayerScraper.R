library(tidyverse)
library(lubridate)
library(rvest)
library(janitor)

urls <- read_csv("url_csvs/ncaa_womens_field_hockey_teamurls_2022.csv") %>% pull(2)

root_url <- "https://stats.ncaa.org"
season = "2022"

playerstatstibble <- tibble(
  team = character(),
  season = character(),
  jersey = character(),
  full_name = character(),
  roster_name = character(),
  last_name = character(),
  first_name = character(),
  yr = character(),
  pos = character(),
  gp = numeric(),
  gs = numeric(),
  goals = numeric(),
  assists = numeric(),
  points = numeric(),
  shot_attempts = numeric(),
  fouls = numeric(),
  red_cards = numeric(),
  yellow_cards = numeric(),
  green_cards = numeric(),
  ggp = numeric(),
  ggs = numeric(),
  minutes = numeric(),
  goals_against = numeric(),
  goals_against_average = numeric(),
  saves = numeric(),
  save_pct = numeric(),
  shutouts = numeric(),
  g_wins = numeric(),
  g_loss = numeric(),
  dsv = numeric(),
  corners = numeric(),
  ps = numeric(),
  psa = numeric(),
  gw = numeric()
)

playerstatsfilename <- paste0("data/ncaa_womens_field_hockey_playerstats_", season, ".csv")

for (i in urls){
  
  schoolpage <- i %>% read_html()
  
  schoolfull <- schoolpage %>% html_nodes(xpath = '//*[@id="contentarea"]/fieldset[1]/legend/a[1]') %>% html_text()
  
  playerstats <- schoolpage %>% html_nodes(xpath = '//*[@id="stat_grid"]') %>% html_table()
  
  playerstats <- tryCatch(playerstats[[1]] %>% clean_names() %>% filter(jersey != "-") %>% rename(blank1 = 13, total_attacks = 14, hit_pct = 15, assists = 16, aces = 17, s_err = 18, digs = 19, r_err = 20, block_solos = 21, block_assists = 22, b_err = 23, total_blocks = 24, pts = 25, bhe = 26, trpl_dbl = 27) %>% mutate(roster_name = player) %>% separate(player, into=c("last_name", "first_name"), sep=",") %>% mutate(full_name = paste(first_name, last_name, sep=" ")) %>% separate(ht, into=c("feet", "inches"), sep="-") %>% mutate(team = schoolfull, season=season) %>% select(team, season, jersey, full_name, roster_name, everything()) %>% mutate_at(vars(-season, -team, -jersey, -full_name, -roster_name, -first_name, -last_name, -yr, -pos), ~str_replace(., ",", "")) %>% mutate(bhe = case_when(is.na(blank1) == TRUE ~ bhe, is.na(blank1) == FALSE ~ total_blocks)) %>% mutate(pts = case_when(is.na(blank1) == TRUE ~ pts, is.na(blank1) == FALSE ~ b_err)) %>% mutate(total_blocks = case_when(is.na(blank1) == TRUE ~ total_blocks, is.na(blank1) == FALSE ~ block_assists)) %>% mutate(b_err = case_when(is.na(blank1) == TRUE ~ b_err, is.na(blank1) == FALSE ~ block_assists)) %>% mutate(block_assists = case_when(is.na(blank1) == TRUE ~ block_assists, is.na(blank1) == FALSE ~ block_solos)) %>% mutate(block_solos = case_when(is.na(blank1) == TRUE ~ block_solos, is.na(blank1) == FALSE ~ r_err)) %>% mutate(r_err = case_when(is.na(blank1) == TRUE ~ r_err, is.na(blank1) == FALSE ~ digs)) %>% mutate(digs = case_when(is.na(blank1) == TRUE ~ digs, is.na(blank1) == FALSE ~ s_err)) %>% mutate(s_err = case_when(is.na(blank1) == TRUE ~ s_err, is.na(blank1) == FALSE ~ aces)) %>% mutate(aces = case_when(is.na(blank1) == TRUE ~ aces, is.na(blank1) == FALSE ~ assists)) %>% mutate(assists = case_when(is.na(blank1) == TRUE ~ assists, is.na(blank1) == FALSE ~ hit_pct)) %>% mutate(hit_pct = case_when(is.na(blank1) == TRUE ~ hit_pct, is.na(blank1) == FALSE ~ total_attacks)) %>% mutate(total_attacks = case_when(is.na(blank1) == TRUE ~ total_attacks, is.na(blank1) == FALSE ~ blank1)) %>% select(-blank1) %>% mutate_all(na_if,"") %>% mutate_at(vars(-season, -team, -jersey, -full_name, -roster_name, -first_name, -last_name, -yr, -pos),  replace_na, '0') %>% mutate_at(vars(-season, -team, -jersey, -full_name, -roster_name, -first_name, -last_name, -yr, -pos), as.numeric),
                          
                          error = function(e){
                            playerstats[[1]] %>% clean_names() %>% filter(jersey != "-") %>% mutate(roster_name = player) %>% separate(player, into=c("last_name", "first_name"), sep=",") %>% mutate(full_name = paste(first_name, last_name, sep=" ")) %>% separate(ht, into=c("feet", "inches"), sep="-") %>% mutate(team = schoolfull, season=season) %>% select(team, season, jersey, full_name, roster_name, everything()) %>% mutate_at(vars(-season, -team, -jersey, -full_name, -roster_name, -first_name, -last_name, -yr, -pos), ~str_replace(., ",", "")) %>% mutate_all(na_if,"") %>% mutate_at(vars(-season, -team, -jersey, -full_name, -roster_name, -first_name, -last_name, -yr, -pos),  replace_na, '0') %>% mutate_at(vars(-season, -team, -jersey, -full_name, -roster_name, -first_name, -last_name, -yr, -pos), as.numeric)
                          })
  
  playerstatstibble <- playerstatstibble %>% add_row(playerstats)
  
  message <- paste0("Fetching ", schoolfull)
  
  print(message)
  
  Sys.sleep(1)
}

write_csv(playerstatstibble, playerstatsfilename)