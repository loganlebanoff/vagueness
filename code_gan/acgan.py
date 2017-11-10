from __future__ import print_function

import numpy as np
import tensorflow as tf
import os
import time
import h5py
from generator_ac import generator
from discriminator_ac import discriminator
import utils
import load
import acgan_model
import argparse
from sklearn import metrics
from scipy.ndimage.interpolation import shift
import sys

prediction_folder = os.path.join('..','predictions')
prediction_words_file = os.path.join('predictions_words_acgan')
summary_file = os.path.join('/home','logan','tmp')
# train_variables_file = os.path.join('../models/tf_enc_dec_variables.npz')
models_folder = os.path.join('..','models')
default_model_name = 'acgan'
use_checkpoint = False
num_folds = 5

start_time = time.time()

FLAGS = tf.app.flags.FLAGS
tf.app.flags.DEFINE_integer('EPOCHS', 51,
                            'Num epochs.')
tf.app.flags.DEFINE_integer('VOCAB_SIZE', 5000,
                            'Number of words in the vocabulary.')
tf.app.flags.DEFINE_integer('LATENT_SIZE', 512,
                            'Size of both the hidden state of RNN and random vector z.')
tf.app.flags.DEFINE_integer('SEQUENCE_LEN', 50,
                            'Max length for each sentence.')
tf.app.flags.DEFINE_integer('EMBEDDING_SIZE', 300,
                            'Max length for each sentence.')
tf.app.flags.DEFINE_integer('PATIENCE', 400,
                            'Max length for each sentence.')
tf.app.flags.DEFINE_integer('BATCH_SIZE', 64,
                            'Max length for each sentence.')
tf.app.flags.DEFINE_integer('NUM_CLASSES', 4,
                            'Max length for each sentence.')
tf.app.flags.DEFINE_integer('CLASS_EMBEDDING_SIZE', 1,
                            'Max length for each sentence.')
tf.app.flags.DEFINE_string('CELL_TYPE', 'GRU',
                            'Which RNN cell for the RNNs.')
tf.app.flags.DEFINE_string('MODE', 'TRAIN',
                            'Whether to run in train or test mode.')
tf.app.flags.DEFINE_boolean('SAMPLE', False,
                            'Whether to sample from the generator distribution to get fake samples.')
tf.app.flags.DEFINE_integer('RANDOM_SEED', 123,
                            'Random seed used for numpy and tensorflow (dropout, sampling)')
tf.app.flags.DEFINE_boolean('USE_CNN', True,
                            'Whether to use CNN or RNN')
tf.app.flags.DEFINE_string("FILTER_SIZES", "3,4,5", 
                            "Comma-separated filter sizes (default: '3,4,5')")
tf.app.flags.DEFINE_integer("NUM_FILTERS", 128, 
                            "Number of filters per filter size (default: 128)")
tf.app.flags.DEFINE_float('KEEP_PROB', 0.5,
                            'Dropout probability of keeping a node')
tf.app.flags.DEFINE_float('HIDDEN_NOISE_STD_DEV', 0, #0.05
                            'Standard deviation for the gaussian noise added to each time '
                            + 'step\'s hidden state. To turn off, set = 0')
tf.app.flags.DEFINE_float('VOCAB_NOISE_STD_DEV', 1,
                            'Standard deviation for the gaussian noise added to each time '
                            + 'step\'s output vocab distr. To turn off, set = 0')
tf.app.flags.DEFINE_float('SOURCE_LOSS_WEIGHT', 0,
                            'How much importance that fake/real contributes to the total loss.')
tf.app.flags.DEFINE_float('REAL_CLASS_LOSS_WEIGHT', 1,
                            'How much importance that real instances\' class loss contributes to the total loss.')
tf.app.flags.DEFINE_float('FAKE_CLASS_LOSS_WEIGHT', 1,
                            'How much importance that real instances\' class loss contributes to the total loss.')
tf.app.flags.DEFINE_boolean('SHARE_EMBEDDING', True,
                            'Whether the discriminator and generator should share their embedding parameters')
tf.app.flags.DEFINE_boolean('TRAIN_GENERATOR', True,
                            'Whether to train the generator\'s parameters')
tf.set_random_seed(FLAGS.RANDOM_SEED)
np.random.seed(FLAGS.RANDOM_SEED)

''' Store model using sampling in a different location ''' 
if FLAGS.SAMPLE:
    default_model_name = 'acgan_sample'

parser = argparse.ArgumentParser()
parser.add_argument("--train_only", help="run in train mode only",
                    action="store_true")
parser.add_argument("--test_only", help="run in test mode only",
                    action="store_true")
parser.add_argument("--one_fold", help="perform only on one fold instead of five-fold cross validation",
                    action="store_true")
parser.add_argument('--name', default=default_model_name, help='Optional name of model, and affects where to save model') 
#     parser.add_argument("--savelocation", help="perform five-fold cross validation",
#                         type=str, action='store_const')
args = parser.parse_args()
'''
--------------------------------

LOAD DATA

--------------------------------
'''
ckpt_dir = os.path.join(models_folder, args.name)

''' Make directories for model files and prediction files '''
utils.create_dirs(ckpt_dir, num_folds)
utils.create_dirs(prediction_folder, num_folds)

params = load.load_pretrained_params()
d, word_to_id = load.load_dictionary()
vague_terms = load.load_vague_terms_vector(word_to_id, FLAGS.VOCAB_SIZE)

Metrics = utils.Metrics()

'''
--------------------------------

MAIN

--------------------------------
'''

def save_samples_to_file(generated_sequences, batch_fake_c, fold_num, epoch):
    fold_prediction_dir = os.path.join(prediction_folder, str(fold_num))
    file_name = os.path.join(fold_prediction_dir, prediction_words_file + '_epoch_' + str(epoch))
    with open(file_name, 'w') as f:
        for i in range(len(generated_sequences)):
            for j in range(len(generated_sequences[i])):
                if generated_sequences[i][j] == 0:
                    f.write('<UNK> ')
                else:
                    word = d[generated_sequences[i][j]]
                    f.write(word + ' ')
            f.write('(' + str(batch_fake_c[i]) + ')\n\n')
            
def sample_Z(m, n):
    return np.zeros((m, n))
#     return np.random.normal(size=[m, n], scale=FLAGS.NOISE_STD_DEV)

def sample_C(m):
    return np.random.randint(low=0, high=FLAGS.NUM_CLASSES, size=m)

def validate(sess, model, val_x, val_y):
    sum_cost = 0
    for batch_x, batch_y, cur, data_len in utils.batch_generator(val_x, val_y, one_hot=not FLAGS.SAMPLE):
        batch_cost = model.run_val(sess, batch_x, batch_y)
        sum_cost += batch_cost * len(batch_y)  # Add up cost based on how many instances in batch
    val_cost = sum_cost / len(val_y)
    return val_cost
    
def train(model, train_x, train_y, val_x, val_y, fold_num):
    print ('building graph')
    if not model.is_built:
        model.build_graph(include_optimizer=True)
    print ('training')
    with tf.Session() as sess:
        train_writer = tf.summary.FileWriter(os.path.join(summary_file + '','train'), sess.graph)
        saver = tf.train.Saver(max_to_keep=2)
        tf.global_variables_initializer().run()
        model.assign_variables(sess)
        min_test_cost = np.inf
        num_mistakes = 0
        
        fold_ckpt_dir = os.path.join(ckpt_dir,str(fold_num))
        gan_variables_file = os.path.join(fold_ckpt_dir,'tf_acgan_variables_')
        if use_checkpoint:
            ckpt = tf.train.get_checkpoint_state(fold_ckpt_dir)
            if ckpt and ckpt.model_checkpoint_path:
                print (ckpt.model_checkpoint_path)
                saver.restore(sess, ckpt.model_checkpoint_path) # restore all variables
    
        start = model.get_global_step() + 1 # get last global_step and start the next one
        print ("Start from:", start)
        
        batch_x, batch_y, _, _ = utils.batch_generator(train_x, train_y, one_hot=not FLAGS.SAMPLE).next()
        batch_fake_c = np.zeros([FLAGS.BATCH_SIZE], dtype=np.int32)
        batch_z = sample_Z(FLAGS.BATCH_SIZE, FLAGS.LATENT_SIZE)
        batch_samples = model.run_samples(sess, batch_fake_c, batch_z)
        save_samples_to_file(batch_samples, batch_fake_c, fold_num, 'pre')
        
        xaxis = 0
        step = 0
        min_val_cost = np.inf
        num_mistakes = 0
        for cur_epoch in range(start, FLAGS.EPOCHS):
            disc_steps = 3
            step_ctr = 0
            for batch_x, batch_y, cur, data_len in utils.batch_generator(train_x, train_y, one_hot=not FLAGS.SAMPLE):
                batch_z = sample_Z(batch_x.shape[0], FLAGS.LATENT_SIZE)
                batch_fake_c = sample_C(batch_x.shape[0])
                for j in range(1):
                    _, D_loss_curr, real_acc, fake_acc, real_class_acc, fake_class_acc, real_loss, fake_loss, real_class_loss, fake_class_loss = model.run_D_train_step(
                        sess, batch_x, batch_y, batch_z, batch_fake_c)
                    print (real_loss, fake_loss, real_class_loss, fake_class_loss)
                    print (real_acc, fake_acc, real_class_acc, fake_class_acc)
                step_ctr += 1
                if step_ctr == disc_steps:
                    step_ctr = 0
                    for j in range(1):
                        batch_z = sample_Z(batch_x.shape[0], FLAGS.LATENT_SIZE)
                        g_batch_fake_c = sample_C(batch_x.shape[0])
                        _, G_loss_curr, batch_samples, batch_probs, summary = model.run_G_train_step(
                            sess, batch_x, batch_y, batch_z, g_batch_fake_c)
            
                    generated_sequences = batch_samples
                    print('Fold', fold_num, 'Epoch: ', cur_epoch,)
                    print('Instance ', cur, ' out of ', data_len)
                    print('D loss: {:.4}'. format(D_loss_curr))
                    print('G_loss: {:.4}'.format(G_loss_curr))
                    print('D real acc: ', real_acc, ' D fake acc: ', fake_acc)
                    print('D real class acc: ', real_class_acc, ' D fake class acc: ', fake_class_acc)
                    print('Samples', generated_sequences)
                    print()
                    for i in range(min(2, len(generated_sequences))):
                        for j in range(len(generated_sequences[i])):
                            if generated_sequences[i][j] == 0:
                                print ('<UNK> ',end='')
                            else:
                                word = d[generated_sequences[i][j]]
                                print (word + ' ',end='')
                        print ('(' + str(g_batch_fake_c[i]) + ')\n')
                     
            train_writer.add_summary(summary, step)
            step += 1
            if cur_epoch % 1 == 0:
                save_samples_to_file(generated_sequences, g_batch_fake_c, fold_num, cur_epoch)
            
            print ('saving model to file:')
    #         global_step.assign(cur_epoch).eval() # set and update(eval) global_step with index, cur_epoch
            model.set_global_step(cur_epoch)
    #         saver.save(sess, fold_ckpt_dir + "/model.ckpt", global_step=global_step)
            saver.save(sess, os.path.join(fold_ckpt_dir,'model.ckpt'), global_step=cur_epoch)
    #         vars = sess.run(tvars)
            vars = model.get_variables(sess)
            tvar_names = [var.name for var in tf.trainable_variables()]
            variables = dict(zip(tvar_names, vars))
            # np.savez(gan_variables_file + str(cur_epoch), **variables)
            np.savez(gan_variables_file, **variables)
            
            val_cost = validate(sess, model, val_x, val_y)
            print('Val Loss: ', val_cost)
            if val_cost < min_val_cost:
                min_val_cost = val_cost
            else:
                num_mistakes += 1
            if num_mistakes >= FLAGS.PATIENCE:
                print ('Stopping early at epoch: ', cur_epoch)
                break
            
        train_writer.close()
            
#         save_samples_to_file(generated_sequences, batch_fake_c, cur_epoch)
    
def test(model, test_x, test_y, fold_num):
    print ('building graph')
    if not model.is_built:
        model.build_graph(include_optimizer=False)
    print ('testing')
    with tf.Session() as sess:
        saver = tf.train.Saver(max_to_keep=5)
        tf.global_variables_initializer().run()
        fold_ckpt_dir = os.path.join(ckpt_dir,str(fold_num))
        ckpt = tf.train.get_checkpoint_state(fold_ckpt_dir)
        if not ckpt:
            raise Exception('Could not find saved model in: ' + fold_ckpt_dir)
        if ckpt and ckpt.model_checkpoint_path:
            print (ckpt.model_checkpoint_path)
            saver.restore(sess, ckpt.model_checkpoint_path) # restore all variables
        predictions = []
        utils.Progress_Bar.startProgress('testing')
        for batch_x, batch_y, cur, data_len in utils.batch_generator(test_x, test_y, batch_size=1, one_hot=not FLAGS.SAMPLE):
#         for batch_x, batch_y, cur, data_len in batch_generator(test_x, test_y):
            batch_predictions = model.run_test(sess, batch_x)
            predictions.append(batch_predictions)
#             print('Instance ', cur, ' out of ', data_len)
            utils.Progress_Bar.progress(float(cur)/float(data_len)*100)
        utils.Progress_Bar.endProgress()
        predictions = np.concatenate(predictions)
        predictions_indices = np.argmax(predictions, axis=1)
        Metrics.print_and_save_metrics(test_y, predictions_indices)
        a=1
    
        
def run_on_fold(mode, model, fold_num):
    train_x, train_y, val_x, val_y, test_x, test_y = load.load_annotated_data(fold_num)
#     args.train = True
    if mode == 'train':
        train(model, train_x, train_y, val_x, val_y, fold_num)
    else:
        test(model, test_x, test_y, fold_num)
        
def run_in_mode(model, mode, one_fold):
    if one_fold:
        run_on_fold(mode, model, 0)
    else:
        for fold_num in range(num_folds):
            run_on_fold(mode, model, fold_num)
        if mode == 'test':
            Metrics.print_metrics_for_all_folds()
    
def main(unused_argv):
    if args.train_only and args.test_only: raise Exception('provide only one mode')
    train = args.train_only or not args.test_only
    test = not args.train_only or args.test_only
    model = acgan_model.ACGANModel(vague_terms, params)
    if train:
        run_in_mode(model, 'train', args.one_fold)
    if test:
        run_in_mode(model, 'test', args.one_fold)
        

    localtime = time.asctime( time.localtime(time.time()) )
    print ("Finished at: ", localtime     )
    print('Execution time: ', (time.time() - start_time)/3600., ' hours')
    
if __name__ == '__main__':
  tf.app.run()
    
    
    
    