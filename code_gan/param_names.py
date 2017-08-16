
TRAIN_EMBEDDING = 'embedding_matrix:0'
TRAIN_GRU_GATES_WEIGHTS = 'rnn/gru_cell/gates/weights:0'
TRAIN_GRU_GATES_BIASES = 'rnn/gru_cell/gates/biases:0'
TRAIN_GRU_CANDIDATE_WEIGHTS = 'rnn/gru_cell/candidate/weights:0'
TRAIN_GRU_CANDIDATE_BIASES = 'rnn/gru_cell/candidate/biases:0'
TRAIN_OUTPUT_WEIGHTS = 'dense/kernel:0'
TRAIN_OUTPUT_BIASES = 'dense/bias:0'

TEST_EMBEDDING = 'embedding_rnn_decoder/embedding:0'
TEST_GRU_GATES_WEIGHTS = 'embedding_rnn_decoder/rnn_decoder/gru_cell/gates/weights:0'
TEST_GRU_GATES_BIASES = 'embedding_rnn_decoder/rnn_decoder/gru_cell/gates/biases:0'
TEST_GRU_CANDIDATE_WEIGHTS = 'embedding_rnn_decoder/rnn_decoder/gru_cell/candidate/weights:0'
TEST_GRU_CANDIDATE_BIASES = 'embedding_rnn_decoder/rnn_decoder/gru_cell/candidate/biases:0'
TEST_OUTPUT_WEIGHTS = 'W:0'
TEST_OUTPUT_BIASES = 'b:0'

EMBEDDING = (TRAIN_EMBEDDING, TEST_EMBEDDING)
GRU_GATES_WEIGHTS = (TRAIN_GRU_GATES_WEIGHTS, TEST_GRU_GATES_WEIGHTS)
GRU_GATES_BIASES = (TRAIN_GRU_GATES_BIASES, TEST_GRU_GATES_BIASES)
GRU_CANDIDATE_WEIGHTS = (TRAIN_GRU_CANDIDATE_WEIGHTS, TEST_GRU_CANDIDATE_WEIGHTS)
GRU_CANDIDATE_BIASES = (TRAIN_GRU_CANDIDATE_BIASES, TEST_GRU_CANDIDATE_BIASES)
OUTPUT_WEIGHTS = (TRAIN_OUTPUT_WEIGHTS, TEST_OUTPUT_WEIGHTS)
OUTPUT_BIASES = (TRAIN_OUTPUT_BIASES, TEST_OUTPUT_BIASES)

LM_VARIABLE_PAIRS = [EMBEDDING, GRU_GATES_WEIGHTS, GRU_GATES_BIASES, 
                     GRU_CANDIDATE_WEIGHTS, GRU_CANDIDATE_BIASES, OUTPUT_WEIGHTS, OUTPUT_BIASES]

# GAN_EMBEDDING



ENC_DEC_TRAIN_EMBEDDING = 'embedding_matrix:0'
ENC_DEC_TRAIN_GRU_GATES_WEIGHTS = 'encoder_decoder/rnn/gru_cell/gates/weights:0'
ENC_DEC_TRAIN_GRU_GATES_BIASES = 'encoder_decoder/rnn/gru_cell/gates/biases:0'
ENC_DEC_TRAIN_GRU_CANDIDATE_WEIGHTS = 'encoder_decoder/rnn/gru_cell/candidate/weights:0'
ENC_DEC_TRAIN_GRU_CANDIDATE_BIASES = 'encoder_decoder/rnn/gru_cell/candidate/biases:0'
ENC_DEC_TRAIN_OUTPUT_WEIGHTS = 'dense/kernel:0'
ENC_DEC_TRAIN_OUTPUT_BIASES = 'dense/bias:0'

